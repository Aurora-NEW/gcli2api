"""
Compatibility routes for CPAMC-style dashboard.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from src.usage_tracker import get_usage_tracker
from src.utils import verify_panel_token


router = APIRouter(prefix="/v0/management", tags=["management-compat"])


@router.get("/usage")
async def get_management_usage(token: str = Depends(verify_panel_token)):
    tracker = get_usage_tracker()
    snapshot = tracker.snapshot()
    return JSONResponse(
        content={
            "usage": snapshot,
            "failed_requests": snapshot.get("failure_count", 0),
        }
    )


@router.get("/openai-compatibility")
async def get_openai_compatibility(token: str = Depends(verify_panel_token)):
    # Placeholder for compatibility with CPAMC dashboards.
    # gcli2 currently does not expose provider-level model disable mapping.
    return JSONResponse(content={"openai-compatibility": []})


@router.patch("/openai-compatibility")
async def patch_openai_compatibility(
    payload: Dict[str, Any] = Body(default_factory=dict),
    token: str = Depends(verify_panel_token),
):
    # Keep endpoint compatible for dashboards that attempt PATCH calls.
    # No-op for now.
    return JSONResponse(content={"status": "ok", "openai-compatibility": []})
