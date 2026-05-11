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

import os

from fastapi import APIRouter, Depends, Request

from atlas.api.openbb.auth import verify_api_key

router = APIRouter()


def _public_base_url(request: Request) -> str:
    """Resolve the public base URL OpenBB Workspace should call back to.

    Priority:
    1. ``OPENBB_PUBLIC_BASE_URL`` env var (set on EC2 in production)
    2. Reconstructed from request headers (works behind cloudflared)
    """
    override = os.environ.get("OPENBB_PUBLIC_BASE_URL", "").rstrip("/")
    if override:
        return override
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    forwarded_proto = request.headers.get("x-forwarded-proto", "https")
    return f"{forwarded_proto}://{forwarded_host}"


def _agent_payload(base_url: str) -> dict:
    return {
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
                "query": f"{base_url}/v1/query",
            },
            "features": {
                "streaming": True,
                "widgets": False,
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
def get_agents_metadata(request: Request) -> dict:
    """Return the Atlas agent definition for OpenBB Workspace registration."""
    return _agent_payload(_public_base_url(request))


@router.get(
    "/v1/widgets.json",
    tags=["openbb"],
    summary="OpenBB widgets manifest (empty — Atlas exposes none in v1)",
)
def get_widgets_manifest() -> dict:
    """Return an empty widgets manifest.

    OpenBB Workspace probes this endpoint during the connect-backend flow
    regardless of the "Validate widgets" toggle. Returning {} satisfies the
    probe; v2 may expose Atlas data widgets here. No auth required — this
    is the same surface area as a public health probe.
    """
    return {}
