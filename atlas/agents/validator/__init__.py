"""Atlas Data Integrity Validator — public API.

Phase A exports:
- ``Finding`` — dataclass representing one detected issue
- ``RuleViolation`` — dataclass from the sensibility rules check
- ``check_value`` — check a single column value against domain constraints
- ``scan_table`` — scan a table and return all sensibility findings
- ``start_run`` / ``finish_run`` / ``upsert_finding`` — persistence helpers

Phase B exports:
- ``TableCoverage`` — dataclass for one table's expected-coverage spec
- ``load_coverage_map`` — parse coverage_map.yaml into TableCoverage list
- ``scan_coverage`` — run schema/coverage checks; returns Finding list

Phase E will add Hermes orchestration on top of these primitives.
"""

from atlas.agents.validator.coverage_loader import TableCoverage, load_coverage_map
from atlas.agents.validator.persistence import finish_run, start_run, upsert_finding
from atlas.agents.validator.schema_scanner import scan_coverage
from atlas.agents.validator.sensibility_rules import RuleViolation, check_value
from atlas.agents.validator.sensibility_scanner import Finding, scan_table

__all__ = [
    "Finding",
    "RuleViolation",
    "TableCoverage",
    "check_value",
    "finish_run",
    "load_coverage_map",
    "scan_coverage",
    "scan_table",
    "start_run",
    "upsert_finding",
]
