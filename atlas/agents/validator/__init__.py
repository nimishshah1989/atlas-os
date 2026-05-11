"""Atlas Data Integrity Validator — public API.

Phase A exports:
- ``Finding`` — dataclass representing one detected issue
- ``RuleViolation`` — dataclass from the sensibility rules check
- ``check_value`` — check a single column value against domain constraints
- ``scan_table`` — scan a table and return all sensibility findings
- ``start_run`` / ``finish_run`` / ``upsert_finding`` — persistence helpers

Phase E will add Hermes orchestration on top of these primitives.
"""

from atlas.agents.validator.persistence import finish_run, start_run, upsert_finding
from atlas.agents.validator.sensibility_rules import RuleViolation, check_value
from atlas.agents.validator.sensibility_scanner import Finding, scan_table

__all__ = [
    "Finding",
    "RuleViolation",
    "check_value",
    "finish_run",
    "scan_table",
    "start_run",
    "upsert_finding",
]
