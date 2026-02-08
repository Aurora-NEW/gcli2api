"""
Usage routes for panel statistics.
"""

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from src.usage_tracker import get_usage_tracker
from src.utils import verify_panel_token


router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/stats")
async def get_usage_stats(token: str = Depends(verify_panel_token)):
    tracker = get_usage_tracker()
    return JSONResponse(content={"success": True, "data": tracker.get_stats_24h()})


@router.get("/aggregated")
async def get_usage_aggregated(token: str = Depends(verify_panel_token)):
    tracker = get_usage_tracker()
    return JSONResponse(content={"success": True, "data": tracker.get_aggregated_24h()})


@router.get("/snapshot")
async def get_usage_snapshot(token: str = Depends(verify_panel_token)):
    tracker = get_usage_tracker()
    return JSONResponse(content={"success": True, "data": tracker.snapshot()})


@router.post("/reset")
async def reset_usage_stats(
    payload: Dict[str, Any] = Body(default_factory=dict),
    token: str = Depends(verify_panel_token),
):
    tracker = get_usage_tracker()
    filename = (payload or {}).get("filename")
    removed = tracker.reset(source=filename)
    if filename:
        message = f"已重置 {filename} 的使用统计（{removed} 条）"
    else:
        message = f"已重置全部使用统计（{removed} 条）"
    return JSONResponse(content={"success": True, "message": message, "removed": removed})
