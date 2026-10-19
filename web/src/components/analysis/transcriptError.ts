// The stored text of a failed LLM call, read into the facts the status
// line shows (owner format 2026-10-19): `{"code": 503, "status":
// "UNAVAILABLE", "message": "The service is currently unavailable."}`.
//
// litellm words a provider failure as `<Error class>: <Provider>Exception
// - {json}`, where the JSON is the provider's own error body — Google's
// is `{"error": {"code", "message", "status"}}`. A text with no such
// body (a plain Python error) becomes one `message` fact holding it all.

// A number stays a number, so a code prints bare (503) and text quoted.
export type CallErrorFact = [key: 'code' | 'status' | 'message', value: string | number | boolean];

const FACT_KEYS: CallErrorFact[0][] = ['code', 'status', 'message'];

// The JSON body inside the text: from its first `{` to its last `}`.
const embeddedJson = (raw: string): Record<string, unknown> | null => {
  const start = raw.indexOf('{');
  const end = raw.lastIndexOf('}');
  if (start < 0 || end <= start) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw.slice(start, end + 1));
    return parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
};

const isScalar = (value: unknown): value is string | number | boolean =>
  typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean';

export const parseCallError = (raw: string): CallErrorFact[] => {
  const body = embeddedJson(raw);
  // Google nests its facts under `error`; others may send them flat.
  const inner = body?.error;
  const source =
    inner !== null && typeof inner === 'object' && !Array.isArray(inner)
      ? (inner as Record<string, unknown>)
      : body;
  const facts: CallErrorFact[] = source
    ? FACT_KEYS.flatMap((key) =>
        isScalar(source[key]) ? [[key, source[key]] as CallErrorFact] : [],
      )
    : [];
  return facts.length > 0 ? facts : [['message', raw.trim()]];
};
