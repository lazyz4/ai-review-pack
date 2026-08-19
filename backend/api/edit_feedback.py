"""POST /api/v1/edit-feedback 路由。

用户在结果页对知识点映射、难度、题型等进行微调，重新评估覆盖率。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.schemas.course import EditFeedbackRequest, GenerateAdvanceResponse
from backend.services.review_pack import apply_topic_edits
from backend.store import get_draft, get_request, save_draft

router = APIRouter(prefix="/edit-feedback", tags=["edit-feedback"])


@router.post("", response_model=GenerateAdvanceResponse, status_code=200, summary="应用用户微调并重新评估覆盖率")
async def edit_feedback(payload: EditFeedbackRequest) -> GenerateAdvanceResponse:
    """应用微调并返回更新版本（outline_version 自动递增）与新的覆盖率。"""
    draft = get_draft(payload.outline_version)
    if draft is None:
        raise HTTPException(
            status_code=404,
            detail=f"未找到 outline_version={payload.outline_version}，请先生成复习包",
        )
    request = get_request(payload.outline_version)
    updated = apply_topic_edits(draft, payload.edits)
    if request is not None:
        save_draft(updated.outline_version, request, updated)
    return updated
