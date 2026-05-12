"""CTS Timing Engine compute primitives.

Public surface: primitives, stage, signals, sector_pivot.
All functions take the whole universe DataFrame and vectorise via groupby.
No Python row loops. All thresholds injected as Mapping[str, Decimal].
"""
