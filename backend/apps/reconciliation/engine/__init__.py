"""
Reconciliation engine — deterministic matching domain logic.

This package is intentionally independent of Django views and HTTP concerns.
It operates on CanonicalTransaction records (or equivalent data) and produces
MatchCandidates with deterministic scoring and evidence metadata.

Components:
    config    — MatchConfig dataclass (tolerance parameters)
    matchers  — candidate generation (reference, amount, date, counterparty)
    scoring   — deterministic composite scoring
    policy    — decision policy (match/conflict/ambiguous/unmatched)
    runner    — orchestrates the full reconciliation pipeline
"""

from .config import MatchConfig
from .runner import ReconciliationEngine

__all__ = ["MatchConfig", "ReconciliationEngine"]
