"""Atlas Data Integrity Validator — public API.

Phase A exports (populated once all sub-modules exist):
- ``Finding`` — dataclass representing one detected issue
- ``RuleViolation`` — dataclass from the sensibility rules check
- ``check_value`` — check a single column value against domain constraints
- ``scan_table`` — scan a table and return all sensibility findings
- ``start_run`` / ``finish_run`` / ``upsert_finding`` — persistence helpers

Phase E will add Hermes orchestration on top of these primitives.
"""
