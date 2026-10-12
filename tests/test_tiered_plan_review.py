# -*- coding: utf-8 -*-
"""Offline tests for the plan review's adjustment rounds (review 2026-10-10).

Two bugs in the check-adjust cycle: a later round's proposal that the
guardrails reject used to erase the earlier ACCEPTED proposal for the
same level (the plan fell back to the computed base, not the accepted
value); and an AI reply that could not be read at all was treated as
the AI saying "no change helps", so the run reported "did not converge"
although no adjustment was ever applied.

The fixture flags exactly one plan-dependent check: the computed stop
(90) rests above the nearest pivot support (89).
"""
from __future__ import annotations

import json
import unittest

from src.tiered_analysis.levels import compute_base_levels
from src.tiered_analysis.plan_review import review_plan
from src.tiered_analysis.providers.base import DataReport, Market, SourceKind
from src.tiered_analysis.schema import Outlook
from src.tiered_analysis.settings import SizingSettings


def _env(value):
    return {"name": "n", "explanation": "e", "value": value}


def _technicals():
    return DataReport(
        name="technicals",
        kind=SourceKind.NUMERIC,
        payload={
            "price": {"close": _env(100.0)},
            "daily": {"sma_50": _env(96.0), "sma_200": _env(90.0)},
            "volatility": {"atr_14": _env(3.0)},
            "levels": {"support_1": _env(89.0)},
        },
    )


#: entry = 96, stop = 90, target = 108; stop 90 >= support 89 flags
#: stop_vs_support, the only plan-dependent check this fixture trips.
BASES = compute_base_levels(close=100.0, sma_50=96.0, sma_200=90.0,
                            support_1=89.0, atr=3.0)


def _adjust(level, value):
    # Reason texts carry no numbers, so no citation is owed.
    return {
        "level": level, "value": value,
        "reasons": [{"check": "stop_vs_support",
                     "text": "Move it where a routine retest cannot reach.",
                     "links": []}],
    }


def _reply(*adjustments):
    return json.dumps({"adjustments": list(adjustments)})


class Scripted:
    """Replies in order; records every prompt."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if not self.replies:
            raise AssertionError(f"unexpected call: {prompt[:80]}")
        return self.replies.pop(0)


def _review(summarizer):
    return review_plan(
        "AAPL", [_technicals()], BASES, Outlook.BULLISH, Market.US,
        SizingSettings(), summarizer=summarizer,
    )


class RejectedLaterProposalTest(unittest.TestCase):
    def test_a_rejected_later_proposal_keeps_the_earlier_accepted_value(self):
        # Round 1: stop → 89 (accepted, but still ON the support, so the
        # check fires again) and target → 110 (accepted). Round 2: stop →
        # 88 (accepted, clears the check) and target → 120 (rejected:
        # 12 away from the 108 base, over the 1 × ATR band).
        fake = Scripted([
            _reply(_adjust("stop_loss", 89.0), _adjust("target", 110.0)),
            _reply(_adjust("stop_loss", 88.0), _adjust("target", 120.0)),
        ])
        review = _review(fake)
        self.assertEqual(len(fake.prompts), 2)
        self.assertAlmostEqual(review.levels.stop_loss, 88.0)
        # The accepted 110 stands — not the computed 108.
        self.assertAlmostEqual(review.levels.target, 110.0)
        self.assertAlmostEqual(
            review.levels_detail["levels"]["target"]["adjusted"], 110.0
        )
        self.assertNotIn("review_failures", review.levels_detail)
        self.assertTrue(any(
            w.startswith("round 2: adjustment for target rejected: ")
            and w.endswith(" — the earlier accepted value 110 kept")
            for w in review.warnings
        ), review.warnings)

    def test_a_rejected_proposal_with_no_earlier_value_falls_back_to_the_base(self):
        # Round 1: stop → 80 (rejected: 10 below the 90 base, over the
        # band) — nothing earlier to keep, so the base stands and the
        # check fires again. Round 2: stop → 88 clears it.
        fake = Scripted([
            _reply(_adjust("stop_loss", 80.0)),
            _reply(_adjust("stop_loss", 88.0)),
        ])
        review = _review(fake)
        self.assertEqual(len(fake.prompts), 2)
        self.assertAlmostEqual(review.levels.stop_loss, 88.0)
        self.assertFalse(any("earlier accepted value" in w for w in review.warnings))


class UnusableReplyTest(unittest.TestCase):
    def test_an_unreadable_reply_is_an_outage_not_no_change_helps(self):
        fake = Scripted(["not json", "still not json"])
        review = _review(fake)
        self.assertEqual(len(fake.prompts), 2)  # the call and its fix round
        self.assertAlmostEqual(review.levels.stop_loss, 90.0)
        self.assertAlmostEqual(review.levels.target, 108.0)
        self.assertIn(
            "round 1: plan review got no usable reply even after a fix round",
            review.warnings,
        )
        self.assertFalse(any("did not converge" in w for w in review.warnings))
        self.assertNotIn("review_failures", review.levels_detail)

    def test_an_explicit_empty_list_is_still_no_change_helps(self):
        review = _review(Scripted([_reply()]))
        self.assertTrue(any("did not converge" in w for w in review.warnings))
        self.assertEqual(
            review.levels_detail["review_failures"],
            [{"round": 1, "checks": ["stop_vs_support"]}],
        )


if __name__ == "__main__":
    unittest.main()
