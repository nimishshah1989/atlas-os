"""SP03: GET /v1/agents.json — OpenBB agent metadata endpoint.

OpenBB Workspace reads this endpoint when a user registers Atlas as a
custom copilot. The response is static — no DB access.

Contract fields per OpenBB BYO Copilot SDK (verify against live docs):
  - name:           Display name in the OpenBB UI
  - description:    Shown in the copilot selector
  - image:          URL to a square icon (PNG or SVG, >= 64x64)
  - endpoints:      Dict of capability name -> URL path
  - features:       Dict of boolean feature flags
  - sample_queries: List of example queries shown in the UI

If the live SDK uses different field names, edit the single
``_AGENT_METADATA`` dict literal below — that is the only place this
contract lives.

Docs: https://docs.openbb.co/workspace/custom-backend/copilot
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from atlas.api.openbb.auth import verify_api_key

router = APIRouter()

# Agent registration payload. Update image URL once the icon is deployed.
_AGENT_METADATA: dict = {
    "atlas": {
        "name": "Atlas Intelligence",
        "description": (
            "Indian equity research engine with relative strength ranking, "
            "momentum classification, market regime detection, and sector "
            "rotation signals. Data covers Nifty 500 universe. All signals "
            "are SEBI-compliant research output."
        ),
        "image": "https://atlas.jslwealth.in/atlas-icon.png",
        "endpoints": {
            "query": "/v1/query",
        },
        "features": {
            "streaming": True,
            "widgets": False,  # v2: can add widget context support
            "citations": False,
        },
        "sample_queries": [
            "What is the current market regime?",
            "Show me the top RS stocks",
            "Which sectors are in the Leading quadrant?",
            "Show me breakout candidates for today",
            "Top RS stocks in the IT sector",
            "What is the sector rotation state?",
        ],
    }
}


@router.get(
    "/v1/agents.json",
    tags=["openbb"],
    summary="OpenBB agent metadata",
    dependencies=[Depends(verify_api_key)],
)
def get_agents_metadata() -> dict:
    """Return the Atlas agent definition for OpenBB Workspace registration."""
    return _AGENT_METADATA
