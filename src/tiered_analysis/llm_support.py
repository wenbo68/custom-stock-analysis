# -*- coding: utf-8 -*-
"""Shared plumbing for the tiered package's own LLM calls (v2).

Used by the level adjuster (slice 3) and the deep analysis (slice 4).
These calls are owned by the tiered package — Tier 1's synthesis happens
inside DSA's decision path, which this package never modifies.

The evidence helpers implement the anchoring contract: LLM claims may only
reference collected evidence — a data_report payload key path that actually
resolves (``technicals.rsi_14``).
"""
from __future__ import annotations

import inspect
import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Type, TypeVar

from pydantic import BaseModel, ValidationError

from src.languages import (
    DEFAULT_LANGUAGE,
    LANGUAGE_RETRY_LIMIT,
    language_name,
    language_problem,
    reply_language_rule,
)

from .providers.base import DataReport
from .run_control import RunStopped

logger = logging.getLogger(__name__)


class LlmConfigError(RuntimeError):
    """LLM configuration missing — callers surface this as a warning."""


#: Transcript rows older than this are pruned at server startup.
TRANSCRIPT_MAX_AGE_DAYS = 14

#: One transcript entry as a plain dict (the storage row's fields).
TranscriptWriter = Callable[[Dict[str, Any]], None]


class LlmTranscript:
    """Record of every LLM exchange in one run.

    One entry per call: stage, llm, the full input and raw output,
    token counts, time, and the error when the call itself raised.
    Exists so a "returned no usable JSON" warning is diagnosable from
    stored evidence instead of a re-run (owner request 2026-08-25).

    Entries go through a ``writer`` — in production the run's rows in
    the ``tiered_run_transcripts`` table (``for_run``), in tests a list.
    ``discard()`` builds a transcript that counts entries and stores
    nothing (CLI runs, harnesses). Any writer failure disables the
    transcript for the rest of the run and is logged; a transcript must
    never fail an analysis (cache convention).
    """

    def __init__(self, run_id: str, writer: Optional[TranscriptWriter] = None) -> None:
        self._run_id = run_id
        self._writer = writer
        self._lock = threading.Lock()
        self._disabled = False
        self._entries = 0

    @classmethod
    def for_run(cls, run_id: str) -> "LlmTranscript":
        """The production transcript: rows keyed by the run's run id."""
        return cls(run_id, writer=_database_transcript_writer(run_id))

    @classmethod
    def discard(cls) -> "LlmTranscript":
        """Counts entries, stores nothing."""
        return cls("", writer=None)

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def entries(self) -> int:
        return self._entries

    def record(
        self,
        *,
        stage: str,
        llm: str,
        temperature: float,
        input: str,
        output: Optional[str],
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        time_ms: Optional[int] = None,
        error: Optional[str] = None,
        structured: Optional[str] = None,
    ) -> None:
        if self._disabled:
            return
        with self._lock:
            entry = {
                "run_id": self._run_id,
                "call_number": self._entries + 1,
                "stage": stage,
                "llm": llm,
                "temperature": temperature,
                "time_ms": time_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                # Which reply enforcement the provider was asked for:
                # "schema" (exact shape), "json" (valid JSON, any keys),
                # or None (prompt-only).
                "structured": structured,
                "error": error,
                "input": input,
                "output": output,
            }
            try:
                if self._writer is not None:
                    self._writer(entry)
                self._entries += 1
            except Exception as exc:
                self._disabled = True
                logger.warning(
                    "LLM transcript write failed (%s) — transcript off for the"
                    " rest of this run",
                    exc,
                )


def _database_transcript_writer(run_id: str) -> TranscriptWriter:
    def write(entry: Dict[str, Any]) -> None:
        from src.storage import DatabaseManager, TieredRunTranscriptRecord

        with DatabaseManager.get_instance().get_session() as session:
            session.add(TieredRunTranscriptRecord(**entry))
            session.commit()

    return write


@dataclass
class _StageUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


#: What the usage numbers cover — stored with them so a reader of an old
#: run is never left guessing. Since 2026-08-10 every LLM stage (the
#: tier-1 preliminary analysis, the deep analysis, the plan review) is a tiered-package
#: call and counted; on older runs the tier-1 blob ran inside the DSA
#: pipeline and was billed there.
USAGE_SCOPE_NOTE = (
    "all tiered-package LLM calls; on runs before 2026-08-10 the tier-1 "
    "synthesis ran inside the DSA pipeline and is not counted"
)

_UNKNOWN_STAGE = "unknown"

_active = threading.local()


class LlmUsageTracker:
    """Per-run LLM call/token counter, grouped by pipeline stage.

    The orchestrator activates one tracker for the run and opens a stage
    around each LLM-using step; ``default_summarizer`` reports into
    whichever tracker is active on the current thread. No tracker active
    (v1 call sites, tests with fake summarizers) → recording is a no-op.

    A ``transcript`` attached here rides the same activation into worker
    threads (they re-``activate()`` the tracker), so every real LLM call
    of the run lands in one file without extra plumbing.

    The run's ``language`` (owner decision 2026-09-26: every sentence a
    reader sees is written in the language the user chose for the app)
    rides here for the same reason: every prompt builder, down to the
    news screens inside the providers, reads it with ``run_language()``
    instead of taking one more argument.

    The run's ``stop`` flag (run_control.py, 2026-10-19) rides here too:
    ``stage`` checks it on entry and ``_summarize`` at the top of every
    LLM call, so a stop reaches the news screens and the vote's worker
    threads through the same activation. None means the run cannot be
    stopped (CLI runs, tests).
    """

    def __init__(
        self,
        transcript: Optional[LlmTranscript] = None,
        language: str = DEFAULT_LANGUAGE,
        stop: Optional[threading.Event] = None,
    ) -> None:
        self._stages: Dict[str, _StageUsage] = {}
        self._current: Optional[str] = None
        self.transcript = transcript
        self.language = language
        self.stop = stop
        # A StopFlag learns which stage it was raised in from here.
        attach = getattr(stop, "attach", None)
        if attach is not None:
            attach(self.current_stage)
        # Deep analysis stages run two LLM calls in parallel threads; both report
        # into the same tracker.
        self._lock = threading.Lock()

    @contextmanager
    def activate(self):
        previous = getattr(_active, "tracker", None)
        _active.tracker = self
        try:
            yield self
        finally:
            _active.tracker = previous

    @contextmanager
    def stage(self, name: str):
        """Label the LLM calls made inside as ``name``'s. A stage never
        begins once the run's stop flag is up (``RunStopped``)."""
        self.checkpoint(name)
        previous = self._current
        self._current = name
        try:
            yield
        finally:
            self._current = previous

    def checkpoint(self, stage: Optional[str] = None) -> None:
        """Raise ``RunStopped`` if the run was asked to stop; a no-op
        for a run without a stop flag. ``stage`` names the step the stop
        lands in — the current stage when not given."""
        if self.stop is not None and self.stop.is_set():
            raise RunStopped(stage or self.current_stage())

    def record(
        self, input_tokens: Optional[int], output_tokens: Optional[int]
    ) -> None:
        with self._lock:
            stage = self._stages.setdefault(
                self._current or _UNKNOWN_STAGE, _StageUsage()
            )
            stage.calls += 1
            stage.input_tokens += int(input_tokens or 0)
            stage.output_tokens += int(output_tokens or 0)

    def current_stage(self) -> str:
        return self._current or _UNKNOWN_STAGE

    def to_detail(self) -> Dict[str, Any]:
        total = _StageUsage()
        for usage in self._stages.values():
            total.calls += usage.calls
            total.input_tokens += usage.input_tokens
            total.output_tokens += usage.output_tokens
        detail: Dict[str, Any] = {
            "stages": {name: u.as_dict() for name, u in self._stages.items()},
            "total": total.as_dict(),
            "scope": USAGE_SCOPE_NOTE,
        }
        # Only a transcript that actually holds entries is worth pointing
        # a reader at — zero-LLM runs (staleness stop) recorded nothing.
        if self.transcript is not None and self.transcript.entries > 0:
            detail["transcript_entries"] = self.transcript.entries
        return detail


def record_llm_usage(
    input_tokens: Optional[int], output_tokens: Optional[int]
) -> None:
    """Report one LLM call to the active tracker, if any."""
    tracker = getattr(_active, "tracker", None)
    if tracker is not None:
        tracker.record(input_tokens, output_tokens)


def active_tracker() -> Optional["LlmUsageTracker"]:
    """The tracker active on this thread, or None.

    The tracker lives in thread-local storage, so code that fans LLM calls
    out to worker threads (the deep analysis's parallel stages) must capture it
    here and re-``activate()`` it inside each worker — otherwise those
    calls silently vanish from the run's usage numbers.
    """
    return getattr(_active, "tracker", None)


def run_language() -> str:
    """The language of the run on this thread — the app's default when
    no tracker is active (v1 call sites, tests with fake summarizers)."""
    tracker = active_tracker()
    return tracker.language if tracker is not None else DEFAULT_LANGUAGE


def language_rule() -> str:
    """The prompt line naming the run's language (``reply_language_rule``)."""
    return reply_language_rule(run_language())


T = TypeVar("T")

_LANGUAGE_RETRY_TEMPLATE = (
    "{prompt}\n\nYour previous reply was invalid: {problem}.\n"
    "Reply again with the same JSON shape, every sentence in {name}; copy "
    "cited values exactly as displayed. JSON only."
)


def in_language(
    ask: Callable[[str], Optional[T]],
    prompt: str,
    texts_of: Callable[[T], Iterable[Optional[str]]],
    stage: str,
    warnings: List[str],
) -> Optional[T]:
    """``ask(prompt)`` once, then again with a correction — up to
    ``LANGUAGE_RETRY_LIMIT`` times — while the reader-facing texts of the
    reply (``texts_of``) are not written in the run's language. The
    check is plain code (src/languages.py); a reply still in the wrong
    language after the retries is kept as written, with a warning, so a
    stubborn model costs wording, never the run.

    ``ask`` is the stage's own validated request (its JSON shape retry
    included) and returns None when that failed. A first reply that never
    parsed ends this loop with None: there is no language to check. A
    RETRY that never parsed does not — the reply already in hand is
    valid, only worded in the wrong language, so it is kept as written
    (with the warning). Returning None there voided a whole stage over
    wording (review 2026-10-10)."""
    language = run_language()
    result = ask(prompt)
    if result is None:
        return None
    retries = 0
    for _attempt in range(LANGUAGE_RETRY_LIMIT):
        problem = language_problem(texts_of(result), language)
        if problem is None:
            return result
        warnings.append(f"{stage} needed a retry — {problem}")
        retries += 1
        retried = ask(_LANGUAGE_RETRY_TEMPLATE.format(
            prompt=prompt, problem=problem, name=language_name(language),
        ))
        if retried is None:
            warnings.append(_kept_as_written(stage, problem, retries))
            return result
        result = retried
    problem = language_problem(texts_of(result), language)
    if problem is not None:
        warnings.append(_kept_as_written(stage, problem, retries))
    return result


def _kept_as_written(stage: str, problem: str, retries: int) -> str:
    """The warning for a reply kept in the wrong language."""
    noun = "retry" if retries == 1 else "retries"
    return f"{stage} {problem} after {retries} {noun} — shown as written"


def _record_transcript(
    tracker: Optional[LlmUsageTracker], **entry: Any
) -> None:
    """One transcript line via the active tracker, stage-attributed.

    No tracker or no transcript (tests, v1 call sites) → no-op, matching
    ``record_llm_usage``.
    """
    if tracker is None or tracker.transcript is None:
        return
    tracker.transcript.record(stage=tracker.current_stage(), **entry)


#: Schema sentinel for reply shapes whose KEYS are decided at run time
#: (the deep analysis's one-vote-per-vote-item-id forms): the provider is asked to
#: guarantee syntactically valid JSON, but the exact keys stay a
#: pydantic-and-retry concern — no portable decode-time schema can name
#: keys that don't exist until the run.
JSON_REPLY = "json"


def _response_format_for(resolved: str, schema: Any) -> Optional[Any]:
    """Translate a caller's expected-reply schema into litellm's
    ``response_format`` — or None when this model can't enforce it.

    ``schema`` is a pydantic model class (the provider then only
    generates JSON matching that exact shape) or ``JSON_REPLY`` (the
    provider guarantees valid JSON, any keys). Any doubt — unknown
    model, capability-lookup error — degrades to None: the prompt still
    asks for JSON, exactly the pre-enforcement behavior.
    """
    import litellm

    try:
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            if litellm.supports_response_schema(model=resolved):
                return schema
            schema = JSON_REPLY  # model can't take a schema; plain JSON mode
        if schema == JSON_REPLY:
            supported = litellm.get_supported_openai_params(model=resolved)
            if supported and "response_format" in supported:
                return {"type": "json_object"}
    except Exception:
        return None
    return None


def _summarize(
    prompt: str,
    temperature: float,
    model: Optional[str] = None,
    schema: Any = None,
) -> str:
    from .run_context import llm_api_key, llm_model

    # A stopped run makes no further call: refused here, before the
    # model is even resolved, so nothing is billed or transcribed.
    tracker = active_tracker()
    if tracker is not None:
        tracker.checkpoint()

    resolved = (model or llm_model() or "").strip()
    if not resolved:
        raise LlmConfigError("no LLM model configured: MAIN_LLM is not set")
    # One provider-agnostic key (LLM_API_KEY) handed to litellm on every
    # call; when it is unset litellm reads the provider's own standard
    # variable (GEMINI_API_KEY, OPENAI_API_KEY, ...) itself.
    api_key = llm_api_key()
    import litellm

    response_format = (
        _response_format_for(resolved, schema) if schema is not None else None
    )
    enforcement: Optional[str] = None
    if response_format is not None:
        enforcement = (
            "schema" if isinstance(response_format, type) else "json"
        )

    started = time.monotonic()

    def _call(fmt: Optional[Any]) -> Any:
        kwargs: Dict[str, Any] = {}
        if fmt is not None:
            kwargs["response_format"] = fmt
        if api_key:
            kwargs["api_key"] = api_key
        return litellm.completion(
            model=resolved,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            **kwargs,
        )

    try:
        try:
            response = _call(response_format)
        except Exception as exc:
            # A provider that rejects the enforcement request itself
            # (HTTP 400) gets one plain call — enforcement is an
            # upgrade and must never break what worked before it.
            if (
                response_format is not None
                and type(exc).__name__ == "BadRequestError"
            ):
                logger.warning(
                    "structured output rejected by %s (%s) — retrying "
                    "without enforcement",
                    resolved,
                    exc,
                )
                enforcement = None
                response = _call(None)
            else:
                raise
    except Exception as exc:
        # The failed call was still a call: it counts toward the run's
        # usage (with no tokens, since none came back) so a stage with
        # only failures does not show 0 calls (review 2026-10-10).
        record_llm_usage(None, None)
        # The failed exchange is exactly what a transcript exists for.
        _record_transcript(
            tracker,
            llm=resolved,
            temperature=temperature,
            input=prompt,
            output=None,
            time_ms=int((time.monotonic() - started) * 1000),
            error=repr(exc),
            structured=enforcement,
        )
        raise
    usage = getattr(response, "usage", None)
    # litellm's usage object speaks the provider's words (prompt_tokens,
    # completion_tokens); everything downstream says input/output tokens.
    record_llm_usage(
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
    )
    raw = response.choices[0].message.content or ""
    _record_transcript(
        tracker,
        llm=resolved,
        temperature=temperature,
        input=prompt,
        output=raw,
        input_tokens=getattr(usage, "prompt_tokens", None),
        output_tokens=getattr(usage, "completion_tokens", None),
        time_ms=int((time.monotonic() - started) * 1000),
        structured=enforcement,
    )
    return raw


def default_summarizer(prompt: str, schema: Any = None) -> str:
    # Temperature 0 everywhere (owner decision 2026-08-23): every LLM
    # stage of a run should repeat as closely as the API allows.
    return _summarize(prompt, temperature=0.0, schema=schema)


def screen_summarizer(prompt: str, schema: Any = None) -> str:
    """Summarizer for the news screen's classification chores.

    A faster, cheaper model — screening is is-this-about-the-company
    bookkeeping, not analysis: ``SUB_LLM``, else the standard
    ``MAIN_LLM`` so unconfigured keeps working. See
    ``run_context.llm_sub_model``. Temperature 0 like every stage.
    """
    from .run_context import llm_sub_model

    return _summarize(prompt, temperature=0.0, model=llm_sub_model(), schema=schema)


def deterministic_summarizer(prompt: str, schema: Any = None) -> str:
    """Zero-temperature summarizer: the scored deep analysis uses it so the
    same evidence grades the same way on every run."""
    return _summarize(prompt, temperature=0.0, schema=schema)


def summarize_with_schema(
    summarize: Callable[..., str], prompt: str, schema: Any
) -> str:
    """Call a summarizer, passing the expected reply schema when it
    accepts one.

    The package's real summarizers take ``schema`` and turn it into
    provider-enforced structured output; injected plain ``(prompt)``
    callables (test fakes, older seams) are called the old way — the
    schema is an upgrade, never a new requirement on the seam.
    """
    if schema is not None:
        try:
            parameters = inspect.signature(summarize).parameters
        except (TypeError, ValueError):
            parameters = {}
        if "schema" in parameters or any(
            p.kind is inspect.Parameter.VAR_KEYWORD
            for p in parameters.values()
        ):
            return summarize(prompt, schema=schema)
    return summarize(prompt)


@dataclass
class StructuredReply:
    """Outcome of one schema-checked LLM request (with one retry)."""

    #: The LAST reply parsed to a dict — None when it wasn't JSON at
    #: all. Handed back even when invalid so callers' tolerant salvage
    #: paths still see whatever came back.
    parsed: Optional[dict]
    #: Whether the last reply passed the pydantic form.
    valid: bool
    #: Whether a second call was made.
    retried: bool
    #: Why the last invalid reply was rejected (None when valid).
    problem: Optional[str]


_STRUCTURED_RETRY_TEMPLATE = (
    "{prompt}\n\nYour previous reply was invalid: {problem}\n"
    "Reply again, following the JSON shape exactly. JSON only."
)


def _validation_problem(exc: ValidationError) -> str:
    """A short retry-friendly reading of a pydantic failure."""
    parts = []
    for error in exc.errors()[:3]:
        where = ".".join(str(piece) for piece in error.get("loc", ()))
        parts.append(f"{where or 'reply'}: {error.get('msg', 'invalid')}")
    return "; ".join(parts) or "reply failed validation"


def request_structured(
    summarize: Callable[..., str],
    prompt: str,
    reply_model: Type[BaseModel],
) -> StructuredReply:
    """One LLM call validated against a pydantic form, with ONE retry
    that shows the model what was wrong (the deep analysis's convention — at
    temperature 0 a bare re-ask would reproduce the same reply).

    Belt and suspenders: the provider is asked to ENFORCE the shape
    while generating (``summarize_with_schema``, when the model supports
    it) and the reply is CHECKED here regardless — a reply that fails
    the form triggers the retry. Exceptions from the call itself
    propagate unretried: transport failures keep their existing
    per-caller fallbacks.
    """
    attempt_prompt = prompt
    parsed: Optional[dict] = None
    problem: Optional[str] = None
    for attempt in range(2):
        raw = summarize_with_schema(summarize, attempt_prompt, reply_model)
        parsed = parse_llm_json(raw)
        if parsed is None:
            problem = "the reply was not a JSON object"
        else:
            try:
                reply_model.model_validate(parsed)
                return StructuredReply(
                    parsed=parsed,
                    valid=True,
                    retried=attempt > 0,
                    problem=None,
                )
            except ValidationError as exc:
                problem = _validation_problem(exc)
        attempt_prompt = _STRUCTURED_RETRY_TEMPLATE.format(
            prompt=prompt, problem=problem
        )
    return StructuredReply(
        parsed=parsed, valid=False, retried=True, problem=problem
    )


def parse_llm_json(raw: str) -> Optional[dict]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def display_value(value: Any) -> str:
    """One number, formatted exactly as the web report pages show it.

    A Python port of the frontend's ``formatValue`` (termHelpers.ts): whole
    numbers stay whole, decimals get 2 places, millions/billions/trillions
    are worded. The v7 deep analysis shows the AI this rendering, requires cited
    values to match it, and checks the claim sentence for the same string —
    so the report page, the sentence, and the check all carry one number.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value).strip()
    magnitude = abs(value)
    if magnitude >= 1e12:
        return f"{value / 1e12:.2f} trillion"
    if magnitude >= 1e9:
        return f"{value / 1e9:.2f} billion"
    if magnitude >= 1e6:
        return f"{value / 1e6:.2f} million"
    if float(value) == int(value):
        return str(int(value))
    return f"{value:.2f}"


def display_payload(node: Any) -> Any:
    """A payload copy with every numeric leaf replaced by its display
    string — what the v7 deep analysis prompts show instead of raw floats."""
    if isinstance(node, dict):
        return {key: display_payload(value) for key, value in node.items()}
    if isinstance(node, bool) or not isinstance(node, (int, float)):
        return node
    return display_value(node)


def evidence_block(data_reports: Sequence[DataReport], display: bool = False) -> str:
    """The evidence bundle LLM stages may cite, with the ref grammar shown.

    ``display=True`` (the v7 deep analysis) renders numeric leaves as their
    report-page display strings so the model cites what the user sees.
    """
    blocks: List[str] = []
    for dim in data_reports:
        if dim.payload:
            payload = display_payload(dim.payload) if display else dim.payload
            blocks.append(
                f"[{dim.name} payload — cite as \"{dim.name}.<key>\"]\n"
                + json.dumps(payload, ensure_ascii=False, default=str)
            )
    return "\n\n".join(blocks) if blocks else "(no evidence collected)"
