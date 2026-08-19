"""Pydantic 请求/响应模型（API Schemas）。

定义 PRD 中三个 API（generate-advance / edit-feedback / export）的
请求体与响应体，保证前后端契约一致。
"""

from __future__ import annotations

from datetime import date as DateType
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

DifficultyName = Literal["easy", "medium", "hard"]
OutputFormat = Literal["WORD", "PDF", "MARKDOWN", "JSON", "IMPORT"]
OutlineSourceName = Literal["PPT", "TEXT"]


class DifficultyWeights(BaseModel):
    """易/中/难题目占比目标。"""

    easy: float = Field(0.3, ge=0.0, le=1.0, description="简单题占比")
    medium: float = Field(0.5, ge=0.0, le=1.0, description="中等题占比")
    hard: float = Field(0.2, ge=0.0, le=1.0, description="难题占比")


class TopicPreferences(BaseModel):
    """可选的生成偏好：覆盖优先级、难度权重与偏好题型。"""

    coverage_priority: Literal["high", "medium", "low"] = Field("high", description="覆盖率优先级")
    difficulty_weight: DifficultyWeights = Field(default_factory=DifficultyWeights, description="难度权重")
    preferred_question_types: list[str] = Field(
        default_factory=lambda: ["multiple_choice", "short_answer", "case_analysis"],
        description="偏好题型列表",
    )


class GenerateAdvanceRequest(BaseModel):
    """POST /api/v1/generate-advance 请求体。"""

    course_id: str = Field(..., min_length=1, max_length=64, examples=["CSE101"])
    course_name: str = Field(..., min_length=1, max_length=128, examples=["软件测试"])
    subject: str = Field(
        "软件测试",
        min_length=1,
        max_length=64,
        description="科目标签（多科目自选，如软件测试、数据结构、高等数学、大学英语等）",
    )
    semester: Optional[str] = Field(None, max_length=32, description="学期，如 2026 秋季")
    outline_source: OutlineSourceName = Field("TEXT", description="大纲来源：PPT 提取文本或直接粘贴")
    outline_content: str = Field(..., min_length=1, description="PPT 提取后的原始文本或粘贴的大纲内容")
    exam_date: Optional[DateType] = Field(None, description="考试日期")
    duration_minutes: int = Field(180, ge=30, le=600, description="考试时长（分钟）")
    output_formats: list[OutputFormat] = Field(default_factory=lambda: ["WORD"], description="期望导出格式")
    topic_preferences: TopicPreferences = Field(default_factory=TopicPreferences, description="题型与覆盖偏好")


class TopicOut(BaseModel):
    """输出用的知识点条目。"""

    topic_id: str
    name: str
    summary: str = ""
    chapter_ref: Optional[str] = None
    difficulty: DifficultyName = "medium"
    is_high_frequency: bool = False
    question_types: list[str] = Field(default_factory=list)
    question_count_range: tuple[int, int] = (2, 5)


class QuestionTemplateOut(BaseModel):
    """题型模板条目。"""

    template_id: str
    topic_id: str
    question_type: str
    stem_template: str
    answer_points: list[str] = Field(default_factory=list)
    analysis_points: list[str] = Field(default_factory=list)
    difficulty: DifficultyName = "medium"
    count_range: tuple[int, int] = (2, 5)


class GeneratedQuestionOut(BaseModel):
    """生成的示例题目条目。"""

    question_id: str
    topic_id: str
    question_type: str
    stem: str
    options: Optional[list[str]] = None
    answer_points: list[str] = Field(default_factory=list)
    analysis_points: list[str] = Field(default_factory=list)
    difficulty: DifficultyName = "medium"


class CoverageMetricsOut(BaseModel):
    """覆盖率统计。"""

    total_topics: int
    covered_topics: int
    coverage_rate: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(0.85, ge=0.0, le=1.0, description="覆盖率阈值")
    meets_threshold: bool = True


class StudyPlanItemOut(BaseModel):
    """学习计划单日条目。"""

    day: int
    date: Optional[DateType] = None
    phase: str = "强化训练"
    focus_topics: list[str] = Field(default_factory=list)
    daily_questions: int
    duration_minutes: int


class StudyPlanDraftOut(BaseModel):
    """个性化学习计划草案。"""

    total_days: int
    start_date: DateType
    end_date: Optional[DateType] = None
    items: list[StudyPlanItemOut] = Field(default_factory=list)


class ExportOptionsOut(BaseModel):
    """可用的导出选项。"""

    available_formats: list[str] = Field(default_factory=list)
    default_format: str = "WORD"
    templates: list[str] = Field(default_factory=lambda: ["default"])
    include_metadata: bool = True


class GenerateAdvanceResponse(BaseModel):
    """POST /api/v1/generate-advance 返回的整合复习包草案。"""

    outline_version: str = "v1.0"
    summary: str
    topics: list[TopicOut] = Field(default_factory=list)
    templates: list[QuestionTemplateOut] = Field(default_factory=list)
    generated_questions: list[GeneratedQuestionOut] = Field(default_factory=list)
    coverage_metrics: CoverageMetricsOut
    study_plan_draft: StudyPlanDraftOut
    export_options: ExportOptionsOut
    created_at: datetime


class TopicEdit(BaseModel):
    """用户在结果页对单个知识点的微调。"""

    topic_id: str
    new_difficulty: Optional[DifficultyName] = None
    new_question_types: Optional[list[str]] = None
    mark_high_frequency: Optional[bool] = None


class EditFeedbackRequest(BaseModel):
    """POST /api/v1/edit-feedback 请求体。"""

    outline_version: str
    edits: list[TopicEdit] = Field(default_factory=list)


class ExportRequest(BaseModel):
    """POST /api/v1/export 请求体。"""

    outline_version: str
    format: OutputFormat = "WORD"
    template: str = "default"
    include_metadata: bool = True


class ExportResponse(BaseModel):
    """POST /api/v1/export 返回体。"""

    file_name: str
    file_size: int
    format: OutputFormat
    download_url: str
    outline_version: str
