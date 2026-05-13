"""Unit tests for atlas.signals.provisioner."""

from __future__ import annotations

from atlas.signals.provisioner import _build_alert_csv_row, _diff_universe

# ---------------------------------------------------------------------------
# _diff_universe tests
# ---------------------------------------------------------------------------


def test_diff_universe_detects_new_tickers() -> None:
    """New tickers in current but not in registered should appear in new set."""
    current = {"A", "B", "C"}
    registered = {"A", "B"}
    new_tickers, removed_tickers = _diff_universe(current, registered)
    assert new_tickers == {"C"}
    assert removed_tickers == set()


def test_diff_universe_detects_removed_tickers() -> None:
    """Tickers in registered but not in current should appear in removed set."""
    current = {"A"}
    registered = {"A", "B"}
    new_tickers, removed_tickers = _diff_universe(current, registered)
    assert new_tickers == set()
    assert removed_tickers == {"B"}


def test_diff_universe_both_directions() -> None:
    """Both new and removed should be detected simultaneously."""
    current = {"A", "C"}
    registered = {"A", "B"}
    new_tickers, removed_tickers = _diff_universe(current, registered)
    assert new_tickers == {"C"}
    assert removed_tickers == {"B"}


def test_diff_universe_empty_current() -> None:
    """All registered tickers removed when current is empty."""
    current: set[str] = set()
    registered = {"A", "B"}
    new_tickers, removed_tickers = _diff_universe(current, registered)
    assert new_tickers == set()
    assert removed_tickers == {"A", "B"}


def test_diff_universe_empty_registered() -> None:
    """All current tickers are new when registry is empty."""
    current = {"A", "B"}
    registered: set[str] = set()
    new_tickers, removed_tickers = _diff_universe(current, registered)
    assert new_tickers == {"A", "B"}
    assert removed_tickers == set()


def test_diff_universe_identical() -> None:
    """No changes when current equals registered."""
    current = {"A", "B"}
    registered = {"A", "B"}
    new_tickers, removed_tickers = _diff_universe(current, registered)
    assert new_tickers == set()
    assert removed_tickers == set()


# ---------------------------------------------------------------------------
# _build_alert_csv_row tests
# ---------------------------------------------------------------------------


def test_build_alert_csv_row_contains_ticker() -> None:
    """CSV row must contain ticker, condition_code, and layout_id."""
    row = _build_alert_csv_row(
        ticker="HDFCBANK",
        exchange="NSE",
        condition_code="breakout_52w_volume",
        chart_type="vs_nifty",
        layout_id="layout-abc-123",
        webhook_url="https://atlas.jslwealth.in/api/v1/tv/signal",
        secret="test-secret",
    )
    assert "HDFCBANK" in row
    assert "breakout_52w_volume" in row
    assert "layout-abc-123" in row


def test_build_alert_csv_row_contains_webhook_url() -> None:
    """CSV row must embed the webhook_url."""
    webhook = "https://atlas.jslwealth.in/api/v1/tv/signal"
    row = _build_alert_csv_row(
        ticker="HDFCBANK",
        exchange="NSE",
        condition_code="breakout_52w_volume",
        chart_type="vs_nifty",
        layout_id="layout-abc-123",
        webhook_url=webhook,
        secret="test-secret",
    )
    assert webhook in row


def test_build_alert_csv_row_escapes_tv_template_vars() -> None:
    """TV template variables must appear as {{close}} in output (not Python f-string format)."""
    row = _build_alert_csv_row(
        ticker="HDFCBANK",
        exchange="NSE",
        condition_code="breakout_52w_volume",
        chart_type="vs_nifty",
        layout_id="layout-abc-123",
        webhook_url="https://atlas.jslwealth.in/api/v1/tv/signal",
        secret="test-secret",
    )
    assert "{{close}}" in row


def test_build_alert_csv_row_format() -> None:
    """CSV row must be comma-separated with symbol as NSE:TICKER."""
    row = _build_alert_csv_row(
        ticker="RELIANCE",
        exchange="NSE",
        condition_code="rs_breakout_52w",
        chart_type="vs_nifty",
        layout_id="layout-xyz",
        webhook_url="https://example.com/hook",
        secret="s3cr3t",
    )
    parts = row.split(",")
    # First field is symbol (EXCHANGE:TICKER)
    assert parts[0] == "NSE:RELIANCE"
    # Second field is condition_code
    assert parts[1] == "rs_breakout_52w"
    # Third field is layout_id
    assert parts[2] == "layout-xyz"


def test_build_alert_csv_row_contains_exchange() -> None:
    """Exchange must appear in the symbol and the message JSON."""
    row = _build_alert_csv_row(
        ticker="TCS",
        exchange="NSE",
        condition_code="breakout_52w_volume",
        chart_type="vs_sector",
        layout_id="lay-sector",
        webhook_url="https://atlas.jslwealth.in/api/v1/tv/signal",
        secret="sec",
    )
    assert "NSE:TCS" in row
    assert '"exchange":"NSE"' in row


def test_build_alert_csv_row_contains_volume_template() -> None:
    """TV {{volume}} template must appear in the message field."""
    row = _build_alert_csv_row(
        ticker="INFY",
        exchange="NSE",
        condition_code="breakout_52w_volume",
        chart_type="vs_nifty",
        layout_id="lay1",
        webhook_url="https://atlas.jslwealth.in/api/v1/tv/signal",
        secret="sec",
    )
    assert "{{volume}}" in row


def test_build_alert_csv_row_contains_time_template() -> None:
    """TV {{timenow}} template must appear in the message field."""
    row = _build_alert_csv_row(
        ticker="INFY",
        exchange="NSE",
        condition_code="breakout_52w_volume",
        chart_type="vs_nifty",
        layout_id="lay1",
        webhook_url="https://atlas.jslwealth.in/api/v1/tv/signal",
        secret="sec",
    )
    assert "{{timenow}}" in row
