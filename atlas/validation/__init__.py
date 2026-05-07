"""Atlas validation framework.

Per ``docs/03_VALIDATION_FRAMEWORK.md`` — five tiers:

- Tier 1: raw data integrity (cross-validate JIP vs external sources)
- Tier 2: computed metrics vs hand-computed reference values
- Tier 3: state classifications vs hand-applied rules
- Tier 4: cross-table consistency (aggregations match constituents)
- Tier 5: daily monitoring (run health, anomaly detection)

This module also includes M1-specific checks like data quality coverage
audits that don't fit the five-tier model but are needed for M1 sign-off.
"""
