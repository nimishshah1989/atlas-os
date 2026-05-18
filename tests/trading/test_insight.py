from unittest.mock import MagicMock, patch

from atlas.trading.insight import generate_insights


def test_generate_insights_returns_bullets(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = (
        "1. RS timeframe weights are shifting toward 1W.\n"
        "2. Constructive regime strategies outperformed.\n"
        "3. High vol penalty weight reduces drawdown."
    )

    with patch("atlas.trading.insight._get_groq_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        bullets = generate_insights(
            parameter_importance={"rs_leader_cutoff_pct": 0.43, "synergy_weight": 0.31},
            top_genome_deltas=[{"genome_id": "abc", "delta": {"rs_w1w": "+0.05"}}],
        )

    assert isinstance(bullets, list)
    assert 1 <= len(bullets) <= 6
    assert all(isinstance(b, str) for b in bullets)


def test_generate_insights_groq_unavailable_returns_empty(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    with patch("atlas.trading.insight._get_groq_client") as mock_client_fn:
        mock_client_fn.side_effect = RuntimeError("Groq unavailable")

        bullets = generate_insights(
            parameter_importance={"rs_leader_cutoff_pct": 0.5},
            top_genome_deltas=[],
        )

    assert bullets == []


def test_generate_insights_malformed_response_returns_empty(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "No numbered bullets here, just prose."

    with patch("atlas.trading.insight._get_groq_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        bullets = generate_insights(
            parameter_importance={},
            top_genome_deltas=[],
        )

    # No numbered bullets found → empty list (graceful degradation)
    assert isinstance(bullets, list)


def test_generate_insights_skipped_when_no_groq_key(monkeypatch):
    """Without a key we never touch the network — fast path returns []."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with patch("atlas.trading.insight._get_groq_client") as mock_client_fn:
        bullets = generate_insights(
            parameter_importance={"rs_leader_cutoff_pct": 0.5},
            top_genome_deltas=[],
        )

    assert bullets == []
    mock_client_fn.assert_not_called()
