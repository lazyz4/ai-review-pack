"""POST /api/v1/generate-advance 路由。

支持两种输入：
- ``POST /api/v1/generate-advance``：直接提交大纲文本；
- ``POST /api/v1/generate-advance/upload``：上传 PPT/PDF/DOCX/TXT 文件。
两者都会调用生成管线（真实调用本地 Ollama）返回整合复习包草案。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from backend.schemas.course import GenerateAdvanceRequest, GenerateAdvanceResponse, TopicPreferences
from backend.services.file_parser import extract_text
from backend.services.review_pack import generate_review_pack
from backend.store import save_draft

router = APIRouter(prefix="/generate-advance", tags=["generate-advance"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.post("", response_model=GenerateAdvanceResponse, status_code=200, summary="生成整合复习包草案")
async def generate_advance(payload: GenerateAdvanceRequest, request: Request) -> GenerateAdvanceResponse:
    """提交大纲文本，解析并生成复习包草案（知识点、模板、示例题、覆盖率、学习计划）。"""
    llm = request.app.state.llm
    response = await generate_review_pack(payload, llm)
    save_draft(response.outline_version, payload, response)
    return response


@router.post("/upload", response_model=GenerateAdvanceResponse, status_code=200, summary="上传大纲文件生成复习包")
async def generate_advance_upload(
    file: UploadFile = File(..., description="支持 .pptx / .pdf / .docx / .txt / .md"),
    course_id: str = Form(..., min_length=1, max_length=64),
    course_name: str = Form(..., min_length=1, max_length=128),
    subject: str = Form("软件测试", description="科目标签（多科目自选）"),
    semester: str = Form("", description="学期"),
    exam_date: str = Form("", description="考试日期 YYYY-MM-DD"),
    duration_minutes: int = Form(180, ge=30, le=600),
    coverage_priority: str = Form("high", description="high / medium / low"),
    preferred_question_types: str = Form(
        "multiple_choice,short_answer,case_analysis",
        description="逗号分隔的偏好题型",
    ),
    request: Request = ...,
) -> GenerateAdvanceResponse:
    """上传 PPT/PDF/DOCX/TXT 文件，提取文本后调用 Ollama 生成复习包。"""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f"文件过大（上限 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB）")
    try:
        outline_content, source = extract_text(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not outline_content:
        raise HTTPException(status_code=400, detail="未能从文件中提取到文本内容，请确认文件不是纯图片型 PDF/PPT")

    parsed_date = None
    if exam_date:
        try:
            parsed_date = date.fromisoformat(exam_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"考试日期格式不正确：{exam_date}（应为 YYYY-MM-DD）") from exc

    priority = coverage_priority if coverage_priority in {"high", "medium", "low"} else "high"
    qtype_list = [item.strip() for item in preferred_question_types.split(",") if item.strip()]
    payload = GenerateAdvanceRequest(
        course_id=course_id,
        course_name=course_name,
        subject=subject or "其他",
        semester=semester or None,
        outline_source="PPT" if source in {"pptx", "ppt"} else "TEXT",
        outline_content=outline_content,
        exam_date=parsed_date,
        duration_minutes=duration_minutes,
        output_formats=["WORD", "PDF", "MARKDOWN", "JSON"],
        topic_preferences=TopicPreferences(
            coverage_priority=priority,
            preferred_question_types=qtype_list,
        ),
    )
    response = await generate_review_pack(payload, request.app.state.llm)
    save_draft(response.outline_version, payload, response)
    return response
