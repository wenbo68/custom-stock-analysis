# -*- coding: utf-8 -*-
"""Offline tests for the sizing settings (v2 slice 6; simplified
2026-09-21).

Every run sizes: the defaults are the web form's own, and the only way
to change them is the per-run override on the request. The old
``.env``-backed layer is gone.
"""
from __future__ import annotations

import unittest

from src.tiered_analysis.settings import (
    DEFAULT_CAPITAL,
    DEFAULT_REWARD_RATIO,
    DEFAULT_RISK_PCT,
    SizingSettings,
    merge_overrides,
)


class TestDefaults(unittest.TestCase):
    def test_bare_settings_are_the_form_defaults_and_enabled(self):
        settings = SizingSettings()
        self.assertTrue(settings.is_enabled)
        self.assertEqual(settings.capital, DEFAULT_CAPITAL)
        self.assertEqual(settings.risk_pct, DEFAULT_RISK_PCT)
        self.assertEqual(settings.reward_ratio, DEFAULT_REWARD_RATIO)

    def test_none_switches_sizing_off_for_tests(self):
        self.assertFalse(SizingSettings(capital=None).is_enabled)
        self.assertFalse(SizingSettings(risk_pct=None).is_enabled)


class TestMergeOverrides(unittest.TestCase):
    def test_overrides_apply_without_mutating_original(self):
        saved = SizingSettings(capital=100000.0, risk_pct=1)
        merged = merge_overrides(saved, capital=25000.0)
        self.assertEqual(merged.capital, 25000.0)
        self.assertEqual(merged.risk_pct, 1)
        self.assertEqual(saved.capital, 100000.0)  # unchanged

    def test_override_can_enable_sizing_for_one_run(self):
        merged = merge_overrides(
            SizingSettings(capital=None, risk_pct=None),
            capital=30000.0, risk_pct=2,
        )
        self.assertTrue(merged.is_enabled)

    def test_no_overrides_returns_equivalent_settings(self):
        saved = SizingSettings(capital=100000.0, risk_pct=1)
        self.assertEqual(merge_overrides(saved), saved)

    def test_reward_at_or_below_one_is_ignored(self):
        merged = merge_overrides(SizingSettings(), reward_ratio=1.0)
        self.assertEqual(merged.reward_ratio, DEFAULT_REWARD_RATIO)
        self.assertEqual(merge_overrides(SizingSettings(), reward_ratio=2.5).reward_ratio, 2.5)


if __name__ == "__main__":
    unittest.main()
