"""Verdict composition — single source of truth for the trader-facing decision label.

Vocabulary lock: BUY / ACCUMULATE / WATCH / HOLD / AVOID / SELL / WAIT
Source of truth: docs/superpowers/specs/2026-05-28-trader-view-redesign.html §4
"""

from atlas.verdict.derive import VerdictInput, VerdictOutput, derive_verdict

__all__ = ["VerdictInput", "VerdictOutput", "derive_verdict"]
