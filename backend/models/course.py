"""课程与知识点 ORM 模型。

一个 ``Course`` 表示学生提交的一份课程大纲（PPT 提取文本或粘贴文本）；
一个 ``Topic`` 表示从该大纲中解析出的单个知识点。两者构成 1:N 关系，
对应 PRD 数据模型中的 Course 1:N Topic 约定。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _new_uuid() -> str:
    """生成一个可用作主键的紧凑 UUID 字符串。"""
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    """返回带时区信息的当前 UTC 时间。"""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """所有 ORM 模型共享的声明式基类。"""


class OutlineSource(str, Enum):
    """大纲文本的来源类型。"""

    PPT = "PPT"
    TEXT = "TEXT"


class Difficulty(str, Enum):
    """知识点或题目的难度等级。"""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionType(str, Enum):
    """支持的题型枚举。"""

    MULTIPLE_CHOICE = "multiple_choice"
    SHORT_ANSWER = "short_answer"
    CASE_ANALYSIS = "case_analysis"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    CODING = "coding"


class Course(Base):
    """一门提交生成复习包的课程。"""

    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    course_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    course_name: Mapped[str] = mapped_column(String(128), index=True)
    semester: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    subject_tag: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    exam_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    outline_source: Mapped[OutlineSource] = mapped_column(String(16), default=OutlineSource.TEXT)
    outline_content: Mapped[str] = mapped_column(Text)
    outline_version: Mapped[str] = mapped_column(String(16), default="v1.0", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    topics: Mapped[list[Topic]] = relationship(
        back_populates="course", cascade="all, delete-orphan", order_by="Topic.order_index"
    )


class Topic(Base):
    """从课程大纲中解析出的单个知识点。"""

    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    topic_id: Mapped[str] = mapped_column(String(32), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    chapter_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    difficulty: Mapped[Difficulty] = mapped_column(String(16), default=Difficulty.MEDIUM)
    is_high_frequency: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    course: Mapped[Course] = relationship(back_populates="topics")
