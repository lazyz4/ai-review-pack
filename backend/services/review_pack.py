"""复习包生成管线。

生成策略：
1. 优先调用本地 Ollama 模型，把大纲解析为知识点、题型模板、示例题、
   覆盖率统计与学习计划草案；
2. 模型返回结果统一经过字段纠偏与 Pydantic 校验；
3. 当 Ollama 不可用或返回数据不合法时，自动降级为确定性启发式生成，
   保证 API 始终可用。
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from backend.schemas.course import (
    CoverageMetricsOut,
    ExportOptionsOut,
    GenerateAdvanceRequest,
    GenerateAdvanceResponse,
    GeneratedQuestionOut,
    QuestionTemplateOut,
    StudyPlanDraftOut,
    StudyPlanItemOut,
    TopicEdit,
    TopicOut,
)
from backend.services.llm_client import LLMClient, LLMError, PROVIDERS

logger = logging.getLogger("review-pack.pipeline")

COVERAGE_THRESHOLD = 0.85
SUPPORTED_QUESTION_TYPES = (
    "multiple_choice",
    "short_answer",
    "case_analysis",
    "true_false",
    "fill_blank",
    "coding",
)
DEFAULT_QUESTION_TYPES = ("multiple_choice", "short_answer", "case_analysis")

TEMPLATE_BANK: dict[str, str] = {
    "multiple_choice": "关于「{name}」，下列哪项表述最符合课程内容？",
    "short_answer": "请结合课堂内容，简要说明「{name}」的核心概念与考查要点。",
    "case_analysis": "给出一个与「{name}」相关的软件测试场景，分析其测试重点与风险。",
    "true_false": "判断以下关于「{name}」的说法是否正确，并说明理由。",
    "fill_blank": "在横线处补全关于「{name}」的关键结论。",
    "coding": "针对「{name}」，设计一个能体现其要点的测试用例或代码片段。",
}

SYSTEM_PROMPT = """你是一名经验丰富的大学课程复习教练，擅长把任意学科的教学大纲转化为可用的复习材料。
用户会提交课程名称、科目标签、大纲文本和生成偏好。请根据科目标签使用对应学科的专业术语，
例如软件测试（用例设计、缺陷管理、性能测试）、数据结构（栈、队列、树、排序）、
高等数学（极限、导数、积分）等。

任务：
1. 把大纲解析为知识点（Topic）清单，按教学逻辑排序，每个知识点给出具体要点摘要；
2. 为每个知识点生成题型模板与覆盖映射；
3. 生成 3-5 道真实的示例题（题干、选项、答案要点、解析要点要符合该学科风格，内容具体专业，不要空泛）；
4. 计算覆盖率（covered_topics / total_topics，目标 ≥ 0.85）；
5. 生成个性化学习计划草案（按考试日期倒排）。

严格只输出一个合法 JSON 对象：不要输出 Markdown 代码块（不要使用 ```），
不要输出任何解释文字、注释或前后缀。
JSON 结构如下：
{
  "summary": "不超过 200 字的执行摘要",
  "topics": [
    {
      "topic_id": "T101",
      "name": "知识点名称",
      "summary": "要点摘要",
      "chapter_ref": "所属大纲章节，可为空",
      "difficulty": "easy | medium | hard",
      "is_high_frequency": false,
      "question_types": ["multiple_choice", "short_answer"],
      "question_count_range": [2, 5]
    }
  ],
  "templates": [
    {
      "template_id": "TPL101",
      "topic_id": "T101",
      "question_type": "multiple_choice",
      "stem_template": "题干模板，可用 {name} 占位",
      "answer_points": ["答案要点"],
      "analysis_points": ["解析要点"],
      "difficulty": "medium",
      "count_range": [2, 5]
    }
  ],
  "generated_questions": [
    {
      "question_id": "Q001",
      "topic_id": "T101",
      "question_type": "multiple_choice",
      "stem": "题干",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer_points": ["正确答案要点"],
      "analysis_points": ["解析要点"],
      "difficulty": "medium"
    }
  ],
  "coverage_metrics": {"total_topics": 0, "covered_topics": 0, "coverage_rate": 0.0},
  "study_plan_draft": {
    "total_days": 7,
    "start_date": "2026-08-19",
    "end_date": "2026-08-25",
    "items": [
      {
        "day": 1,
        "date": "2026-08-19",
        "phase": "基础梳理",
        "focus_topics": ["T101"],
        "daily_questions": 12,
        "duration_minutes": 90
      }
    ]
  }
}

知识点数量应与大纲规模匹配；覆盖率至少达到 0.85；示例题 3-5 道。
知识点名称、题干、答案与解析请使用中文或该课程的实际语言。

输出保持精炼（整份 JSON 控制在 1500 tokens 以内）：
- 知识点不超过 15 个，每个知识点 summary 不超过 40 字；
- 每个知识点只生成 1 个题型模板，answer_points / analysis_points 各 1-2 条短语；
- 示例题只生成 3 道，每道解析不超过 50 字；
- 不要重复大纲原文，不要输出解释文字。"""

MAX_OUTLINE_CHARS = 12000


async def generate_review_pack(
    request: GenerateAdvanceRequest,
    llm: LLMClient,
    overrides: dict[str, str] | None = None,
    is_demo: bool = False,
) -> GenerateAdvanceResponse:
    """生成整合复习包草案。

    优先使用请求级 BYOK 配置（用户自己的 API Key / 服务商 / 模型）；
    云端服务商缺 Key 或 Key 无效时返回明确报错；
    模型输出无法解析或 Ollama 不可用时自动降级为启发式生成，保证页面始终可用。
    """
    overrides = overrides or {}
    provider = (overrides.get("provider") or llm.provider or "ollama").lower()
    api_key = llm.effective_api_key(provider, overrides.get("api_key") or "")

    if provider == "custom" and not overrides.get("base_url"):
        raise LLMError("自定义服务商需要填写 Base URL（例如 https://api.example.com/v1）")
    if provider not in PROVIDERS and provider != "custom":
        raise LLMError(f"未知服务商：{provider}")
    if provider != "ollama" and provider != "custom" and not api_key:
        label = PROVIDERS.get(provider, {}).get("label", provider)
        raise LLMError(
            f"没有可用的 {label} API Key：请在页面“模型设置”中填写你自己的 Key"
            "（选择 DeepSeek 且不填 Key 时，演示账号默认使用部署方配置的服务端 Key）"
        )

    if provider == "ollama":
        ok, message, _ = await llm.verify(
            provider="ollama",
            base_url=overrides.get("base_url"),
            model=overrides.get("model"),
        )
        if not ok:
            logger.warning("Ollama 不可用，切换到启发式生成：%s", message)
            return _fallback_response(request)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(request)},
    ]
    last_parse_error = ""
    for attempt in range(2):
        raw_text = ""
        try:
            raw_text = await llm.chat(messages, temperature=0.3, max_tokens=2048, **overrides)
            data = _extract_json(raw_text)
            result = _response_from_data(request, data)
            logger.info(
                "LLM 生成成功（%s）：%d 个知识点，%d 道示例题，覆盖率 %.0f%%",
                provider,
                len(result.topics),
                len(result.generated_questions),
                result.coverage_metrics.coverage_rate * 100,
            )
            return result
        except LLMError as exc:
            if provider != "ollama":
                raise
            logger.warning("Ollama 第 %d 次生成失败：%s", attempt + 1, exc)
        except Exception as exc:  # noqa: BLE001 - 降级路径需要捕获一切解析异常
            last_parse_error = str(exc)
            logger.warning("第 %d 次生成解析失败：%s", attempt + 1, exc)
            if attempt == 0 and raw_text:
                messages.append({"role": "assistant", "content": raw_text[:3000]})
                messages.append(
                    {"role": "user", "content": "上次输出不是合法 JSON。请只输出一个合法 JSON 对象，不要 Markdown 代码块。"}
                )
    if provider == "ollama":
        logger.warning("Ollama 两次生成失败，切换到启发式生成")
        return _fallback_response(request)
    # 云端模型输出无法解析：不直接报 502，降级为启发式生成并说明原因，保证页面可用
    logger.warning("%s 两次生成结果无法解析，切换到启发式生成：%s", provider, last_parse_error)
    fallback = _fallback_response(request)
    label = PROVIDERS.get(provider, {}).get("label", provider)
    fallback.summary += (
        f"（{label} 返回内容无法解析为复习包 JSON，已自动降级为本地启发式生成："
        f"{last_parse_error or '未知原因'}。可检查 Key/模型设置后重试）"
    )
    return fallback


def apply_topic_edits(draft: GenerateAdvanceResponse, edits: list[TopicEdit]) -> GenerateAdvanceResponse:
    """应用用户的逐点微调并重新评估覆盖率，返回新版本草案。"""
    topics_by_id = {topic.topic_id: topic for topic in draft.topics}
    changed = False
    for edit in edits:
        topic = topics_by_id.get(edit.topic_id)
        if topic is None:
            continue
        if edit.new_difficulty is not None and edit.new_difficulty != topic.difficulty:
            topic.difficulty = edit.new_difficulty
            changed = True
        if edit.new_question_types is not None:
            cleaned = [qtype for qtype in edit.new_question_types if qtype in SUPPORTED_QUESTION_TYPES]
            if cleaned != topic.question_types:
                topic.question_types = cleaned
                changed = True
        if edit.mark_high_frequency is not None and edit.mark_high_frequency != topic.is_high_frequency:
            topic.is_high_frequency = edit.mark_high_frequency
            changed = True
    if changed:
        # 同步重建每个知识点的题型模板：保留仍选中的题型，补齐新选的题型
        rebuilt: list[QuestionTemplateOut] = []
        for topic in draft.topics:
            topic_templates = [tpl for tpl in draft.templates if tpl.topic_id == topic.topic_id]
            keep = [tpl for tpl in topic_templates if tpl.question_type in topic.question_types]
            for tpl in keep:
                tpl.difficulty = topic.difficulty
            covered = {tpl.question_type for tpl in keep}
            missing = [qtype for qtype in topic.question_types if qtype not in covered]
            rebuilt.extend(keep)
            rebuilt.extend(tpl for tpl in _fallback_templates(topic) if tpl.question_type in missing)
        draft.templates = rebuilt
        draft.coverage_metrics = _coverage(draft.topics)
        draft.outline_version = _bump_version(draft.outline_version)
    draft.created_at = datetime.now(timezone.utc)
    return draft


def _build_user_prompt(request: GenerateAdvanceRequest) -> str:
    """把请求组装为发给 Ollama 的用户提示词。"""
    preferences = request.topic_preferences
    outline = request.outline_content
    if len(outline) > MAX_OUTLINE_CHARS:
        outline = outline[:MAX_OUTLINE_CHARS] + "\n…（大纲过长，已截断）"
    parts = [
        f"课程名称：{request.course_name}",
        f"课程代码：{request.course_id}",
        f"科目标签：{request.subject}",
        f"学期：{request.semester or '未指定'}",
        f"大纲来源：{request.outline_source}",
        f"考试日期：{request.exam_date or '未指定'}",
        f"考试时长（分钟）：{request.duration_minutes}",
        f"覆盖优先级：{preferences.coverage_priority}",
        f"难度权重：{preferences.difficulty_weight.model_dump_json()}",
        f"偏好题型：{', '.join(preferences.preferred_question_types)}",
        "=== 大纲文本开始 ===",
        outline,
        "=== 大纲文本结束 ===",
    ]
    return "\n".join(parts)


def _extract_json(text: str) -> dict[str, Any]:
    """从模型输出中提取第一个完整、合法的 JSON 对象。

    兼容 Markdown 代码块、前后缀说明文字，以及 JSON 之后又出现花括号的情况：
    按字符串感知的方式配对花括号，取第一个能通过 json.loads 的完整对象。
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = None
    while start != -1:
        try:
            candidate, end = _balanced_json_object(text, start)
            return json.loads(candidate)
        except ValueError:
            # 该段不是合法 JSON，继续找下一个 “{”
            start = text.find("{", end + 1 if end is not None else start + 1)
    raise ValueError("模型响应中未找到合法 JSON 对象")


def _balanced_json_object(text: str, start: int) -> tuple[str, int]:
    """从 start 处的 “{” 出发，返回（首个完整 JSON 对象文本, 结束下标）。

    花括号配对时忽略 JSON 字符串内部的括号（含转义），确保不会把
    模型输出末尾解释文字里的花括号误当成 JSON 结尾。
    """
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1], index
    raise ValueError("模型响应中未找到完整的 JSON 对象")


def _response_from_data(request: GenerateAdvanceRequest, data: dict[str, Any]) -> GenerateAdvanceResponse:
    """把 LLM 返回的 JSON 字典规整为 Pydantic 响应模型。"""
    topics: list[TopicOut] = []
    for index, raw in enumerate(data.get("topics") or []):
        if not isinstance(raw, dict):
            continue
        try:
            topics.append(_topic_from_raw(raw, index))
        except (TypeError, ValueError):
            continue
    if not topics:
        raise ValueError("LLM 未返回有效知识点")

    templates: list[QuestionTemplateOut] = []
    for raw in data.get("templates") or []:
        if not isinstance(raw, dict):
            continue
        try:
            templates.append(_template_from_raw(raw))
        except (TypeError, ValueError):
            continue
    if not templates:
        templates = [template for topic in topics for template in _fallback_templates(topic)]
    else:
        covered_topic_ids = {template.topic_id for template in templates}
        for topic in topics:
            if topic.topic_id not in covered_topic_ids:
                templates.extend(_fallback_templates(topic))

    questions: list[GeneratedQuestionOut] = []
    for raw in data.get("generated_questions") or []:
        if not isinstance(raw, dict):
            continue
        try:
            questions.append(_question_from_raw(raw))
        except (TypeError, ValueError):
            continue
    if not questions:
        questions = _fallback_questions(topics, request.topic_preferences)

    topics_by_id = {topic.topic_id: topic for topic in topics}
    for template in templates:
        topic = topics_by_id.get(template.topic_id)
        if topic is not None:
            template.stem_template = template.stem_template.replace("{name}", topic.name)
    for question in questions:
        topic = topics_by_id.get(question.topic_id)
        if topic is not None:
            question.stem = question.stem.replace("{name}", topic.name)
            question.options = [option.replace("{name}", topic.name) for option in question.options] if question.options else None
            question.answer_points = [point.replace("{name}", topic.name) for point in question.answer_points]
            question.analysis_points = [point.replace("{name}", topic.name) for point in question.analysis_points]
            if any(point in {"正确答案要点", "答案要点"} for point in question.answer_points):
                question.answer_points = [topic.summary, "结合课程定义与典型解法作答"]
            if any(point == "解析要点" for point in question.analysis_points):
                question.analysis_points = [f"先回顾「{topic.name}」的定义与性质，再代入题目条件逐步求解"]

    coverage_raw = data.get("coverage_metrics")
    coverage = _coverage_from_raw(coverage_raw, topics) if isinstance(coverage_raw, dict) else _coverage(topics)
    plan = _study_plan(topics, request.exam_date, request.duration_minutes, data.get("study_plan_draft"))
    summary = str(data.get("summary") or "").strip()
    if len(summary) < 20:
        names = "、".join(topic.name for topic in topics[:8])
        summary = (
            f"本复习包围绕「{names}」等 {len(topics)} 个知识点展开，"
            f"当前覆盖率 {coverage.coverage_rate:.0%}，可用于考前系统复习与自测。"
        )
    return GenerateAdvanceResponse(
        outline_version="v1.0",
        summary=summary,
        topics=topics,
        templates=templates,
        generated_questions=questions,
        coverage_metrics=coverage,
        study_plan_draft=plan,
        export_options=ExportOptionsOut(
            available_formats=["WORD", "PDF", "MARKDOWN", "JSON"],
            default_format="WORD",
            templates=["default"],
            include_metadata=True,
        ),
        created_at=datetime.now(timezone.utc),
    )


def _fallback_response(request: GenerateAdvanceRequest) -> GenerateAdvanceResponse:
    """确定性启发式生成，保证 Ollama 不可用时 API 仍可用。"""
    lines = _parse_outline_lines(request.outline_content)
    if not lines:
        lines = ["软件测试基本概念", "测试用例设计方法", "缺陷生命周期", "性能测试入门"]
    topics = [_fallback_topic(line, index, request.topic_preferences) for index, line in enumerate(lines[:80])]
    templates = [template for topic in topics for template in _fallback_templates(topic)]
    questions = _fallback_questions(topics, request.topic_preferences)
    coverage = _coverage(topics)
    plan = _study_plan(topics, request.exam_date, request.duration_minutes)
    summary = (
        f"科目《{request.subject}》：已从 {request.outline_source} 大纲中解析出 {len(topics)} 个知识点，"
        f"覆盖率 {coverage.coverage_rate:.0%}，共生成 {len(templates)} 个题型模板"
        f"与 {len(questions)} 道示例题。当前为本地启发式生成，"
        "启动 Ollama 后可获得更高质量内容。"
    )
    return GenerateAdvanceResponse(
        outline_version="v1.0",
        summary=summary,
        topics=topics,
        templates=templates,
        generated_questions=questions,
        coverage_metrics=coverage,
        study_plan_draft=plan,
        export_options=ExportOptionsOut(
            available_formats=["WORD", "PDF", "MARKDOWN", "JSON"],
            default_format="WORD",
            templates=["default"],
            include_metadata=True,
        ),
        created_at=datetime.now(timezone.utc),
    )


def _parse_outline_lines(outline: str) -> list[str]:
    """把大纲文本切成知识点候选行，并去掉编号与列表符号。"""
    lines: list[str] = []
    for raw in outline.splitlines():
        line = raw.strip()
        line = re.sub(r"^[\d一二三四五六七八九十]+[、.．\)）]\s*", "", line)
        line = line.strip(" -•·　")
        if len(line) >= 2:
            lines.append(line)
    return lines


def _fallback_topic(line: str, index: int, preferences: Any) -> TopicOut:
    """根据行文本启发式生成一个知识点。"""
    if any(keyword in line for keyword in ("综合", "分析", "设计", "推导", "证明", "算法", "压测", "性能", "并发", "安全")):
        difficulty = "hard"
    elif any(keyword in line for keyword in ("概念", "定义", "概述", "基础", "引言", "介绍", "绪论", "导论")):
        difficulty = "easy"
    else:
        difficulty = "medium"
    preferred = [qtype for qtype in preferences.preferred_question_types if qtype in SUPPORTED_QUESTION_TYPES]
    if not preferred:
        preferred = list(DEFAULT_QUESTION_TYPES)
    types = list(dict.fromkeys([preferred[index % len(preferred)], preferred[(index + 1) % len(preferred)]]))
    high_frequency = any(keyword in line for keyword in ("高频", "重点", "常考", "核心"))
    return TopicOut(
        topic_id=f"T{index + 1:03d}",
        name=line,
        summary=f"本知识点聚焦“{line}”的核心概念、常见考点与易错点。",
        chapter_ref=None,
        difficulty=difficulty,
        is_high_frequency=high_frequency,
        question_types=types,
        question_count_range=(3, 6) if high_frequency else (2, 4),
    )


def _fallback_templates(topic: TopicOut) -> list[QuestionTemplateOut]:
    """为知识点生成题型模板。"""
    templates: list[QuestionTemplateOut] = []
    for qtype in topic.question_types:
        stem = TEMPLATE_BANK.get(qtype, "请回答：{name}").format(name=topic.name)
        templates.append(
            QuestionTemplateOut(
                template_id=f"TPL{topic.topic_id[-3:]}_{qtype[:2].upper()}",
                topic_id=topic.topic_id,
                question_type=qtype,
                stem_template=stem,
                answer_points=[topic.summary, "结合课程定义与典型例题作答"],
                analysis_points=["先定位考点所属章节", "按“概念 → 应用 → 易错点”三步展开"],
                difficulty=topic.difficulty,
                count_range=topic.question_count_range,
            )
        )
    return templates


def _fallback_questions(topics: list[TopicOut], preferences: Any) -> list[GeneratedQuestionOut]:
    """按 PRD 约定生成 3-5 道示例题。"""
    questions: list[GeneratedQuestionOut] = []
    for topic in topics[:5]:
        qtype = topic.question_types[0]
        if qtype == "multiple_choice":
            questions.append(
                GeneratedQuestionOut(
                    question_id=f"Q{len(questions) + 1:03d}",
                    topic_id=topic.topic_id,
                    question_type=qtype,
                    stem=TEMPLATE_BANK[qtype].format(name=topic.name),
                    options=[
                        "A. 与课程讲义一致的正确表述",
                        "B. 与课程定义相悖的表述",
                        "C. 偷换概念后的错误表述",
                        "D. 过于绝对化的表述",
                    ],
                    answer_points=["A", topic.summary],
                    analysis_points=["对照讲义中“{name}”的定义".format(name=topic.name), "排除绝对化与偷换概念的选项"],
                    difficulty=topic.difficulty,
                )
            )
        else:
            questions.append(
                GeneratedQuestionOut(
                    question_id=f"Q{len(questions) + 1:03d}",
                    topic_id=topic.topic_id,
                    question_type=qtype,
                    stem=TEMPLATE_BANK[qtype].format(name=topic.name),
                    options=None,
                    answer_points=[topic.summary, "结合实例说明"],
                    analysis_points=["抓住题干中的测试场景关键词", "按“要点 + 依据 + 结论”组织答案"],
                    difficulty=topic.difficulty,
                )
            )
    return questions


def _coverage(topics: list[TopicOut]) -> CoverageMetricsOut:
    """根据每个知识点是否保有题型模板计算覆盖率。"""
    total = len(topics)
    covered = sum(1 for topic in topics if topic.question_types)
    rate = round(covered / total, 4) if total else 0.0
    return CoverageMetricsOut(
        total_topics=total,
        covered_topics=covered,
        coverage_rate=rate,
        threshold=COVERAGE_THRESHOLD,
        meets_threshold=rate >= COVERAGE_THRESHOLD,
    )


def _coverage_from_raw(raw: dict[str, Any], topics: list[TopicOut]) -> CoverageMetricsOut:
    """采纳 LLM 的覆盖率，若与知识点数量不一致则重新计算。"""
    total = _int(raw.get("total_topics"), len(topics))
    covered = _int(raw.get("covered_topics"), 0)
    rate = _float(raw.get("coverage_rate"), 0.0)
    if total != len(topics) or not 0.0 <= rate <= 1.0:
        return _coverage(topics)
    rate = round(rate, 4)
    return CoverageMetricsOut(
        total_topics=total,
        covered_topics=covered,
        coverage_rate=rate,
        threshold=COVERAGE_THRESHOLD,
        meets_threshold=rate >= COVERAGE_THRESHOLD,
    )


def _study_plan(
    topics: list[TopicOut],
    exam_date: Optional[date],
    duration_minutes: int,
    data: Optional[dict[str, Any]] = None,
) -> StudyPlanDraftOut:
    """生成个性化学习计划草案；LLM 数据存在时优先采用并校验。"""
    today = date.today()
    if isinstance(data, dict) and data.get("items"):
        items: list[StudyPlanItemOut] = []
        for raw in data["items"]:
            if not isinstance(raw, dict):
                continue
            try:
                item_date = date.fromisoformat(str(raw["date"])) if raw.get("date") else None
                items.append(
                    StudyPlanItemOut(
                        day=_int(raw.get("day"), len(items) + 1),
                        date=item_date,
                        phase=str(raw.get("phase") or "强化训练"),
                        focus_topics=_str_list(raw.get("focus_topics")) or [topic.topic_id for topic in topics[:1]],
                        daily_questions=_int(raw.get("daily_questions"), 10),
                        duration_minutes=_int(raw.get("duration_minutes"), duration_minutes),
                    )
                )
            except (TypeError, ValueError):
                continue
        if items:
            start = items[0].date or today
            end = items[-1].date or start
            return StudyPlanDraftOut(total_days=len(items), start_date=start, end_date=end, items=items)

    if exam_date and exam_date >= today:
        days = min(max((exam_date - today).days + 1, 3), 14)
    else:
        days = 7
    start = today
    size = math.ceil(len(topics) / days) if topics else 0
    chunks = [topics[index : index + size] for index in range(0, len(topics), size)][:days]
    items = [
        _plan_item(index + 1, start + timedelta(days=index), chunk, days, duration_minutes)
        for index, chunk in enumerate(chunks)
    ]
    end = start + timedelta(days=len(items) - 1) if items else start
    return StudyPlanDraftOut(total_days=len(items), start_date=start, end_date=end, items=items)


def _plan_item(day: int, day_date: date, topics: list[TopicOut], total_days: int, duration_minutes: int) -> StudyPlanItemOut:
    """生成单日学习计划条目。"""
    ratio = (day - 1) / max(total_days - 1, 1)
    if ratio < 0.35:
        phase = "基础梳理"
    elif ratio < 0.75:
        phase = "强化训练"
    else:
        phase = "冲刺模拟"
    daily_questions = min(max(duration_minutes // 15, 5), 20)
    return StudyPlanItemOut(
        day=day,
        date=day_date,
        phase=phase,
        focus_topics=[topic.topic_id for topic in topics],
        daily_questions=daily_questions,
        duration_minutes=min(max(duration_minutes // total_days, 30), 180),
    )


def _topic_from_raw(raw: dict[str, Any], index: int) -> TopicOut:
    """把 LLM 输出的知识点字典规整为 TopicOut。"""
    qtypes = _str_list(raw.get("question_types"))
    if not qtypes:
        qtypes = [DEFAULT_QUESTION_TYPES[index % len(DEFAULT_QUESTION_TYPES)]]
    lo, hi = _count_range(raw.get("question_count_range"), (2, 5))
    return TopicOut(
        topic_id=str(raw.get("topic_id") or f"T{index + 1:03d}"),
        name=str(raw.get("name") or f"知识点 {index + 1}"),
        summary=str(raw.get("summary") or ""),
        chapter_ref=str(raw["chapter_ref"]) if raw.get("chapter_ref") else None,
        difficulty=_difficulty(raw.get("difficulty")),
        is_high_frequency=_bool(raw.get("is_high_frequency")),
        question_types=qtypes,
        question_count_range=(lo, hi),
    )


def _template_from_raw(raw: dict[str, Any]) -> QuestionTemplateOut:
    """把 LLM 输出的模板字典规整为 QuestionTemplateOut。"""
    topic_id = str(raw.get("topic_id") or "")
    qtype = str(raw.get("question_type") or DEFAULT_QUESTION_TYPES[0])
    stem = str(
        raw.get("stem_template")
        or TEMPLATE_BANK.get(qtype, "请回答：{name}").format(name=str(raw.get("name") or topic_id))
    )
    lo, hi = _count_range(raw.get("count_range"), (2, 5))
    return QuestionTemplateOut(
        template_id=str(raw.get("template_id") or f"TPL{topic_id[-3:]}_{qtype[:2].upper()}"),
        topic_id=topic_id,
        question_type=qtype,
        stem_template=stem,
        answer_points=_str_list(raw.get("answer_points")) or ["答案要点"],
        analysis_points=_str_list(raw.get("analysis_points")) or ["解析要点"],
        difficulty=_difficulty(raw.get("difficulty")),
        count_range=(lo, hi),
    )


def _question_from_raw(raw: dict[str, Any]) -> GeneratedQuestionOut:
    """把 LLM 输出的题目字典规整为 GeneratedQuestionOut。"""
    options = _str_list(raw.get("options"))
    return GeneratedQuestionOut(
        question_id=str(raw.get("question_id") or "Q000"),
        topic_id=str(raw.get("topic_id") or ""),
        question_type=str(raw.get("question_type") or "short_answer"),
        stem=str(raw.get("stem") or ""),
        options=options or None,
        answer_points=_str_list(raw.get("answer_points")) or ["答案要点"],
        analysis_points=_str_list(raw.get("analysis_points")) or ["解析要点"],
        difficulty=_difficulty(raw.get("difficulty")),
    )


def _bump_version(version: str) -> str:
    """把版本号 v1.0 提升为 v1.1。"""
    digits = re.findall(r"\d+", version)
    if not digits:
        return "v1.1"
    major = int(digits[0])
    minor = int(digits[1]) if len(digits) > 1 else 0
    return f"v{major}.{minor + 1}"


def _count_range(value: Any, default: tuple[int, int]) -> tuple[int, int]:
    """把 [2, 5] 之类的内容规整为有序区间。"""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        lo = _int(value[0], default[0])
        hi = _int(value[1], default[1])
        return (min(lo, hi), max(lo, hi))
    return default


def _difficulty(value: Any) -> str:
    """规整难度字段。"""
    raw = str(value or "medium").strip().lower()
    return raw if raw in {"easy", "medium", "hard"} else "medium"


def _bool(value: Any, default: bool = False) -> bool:
    """宽松地把任意值转换为布尔。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "是", "高频"}
    return default


def _str_list(value: Any) -> list[str]:
    """把任意值规整为字符串列表。"""
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _int(value: Any, default: int) -> int:
    """把任意值转换为整数，失败时返回默认值。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    """把任意值转换为浮点数，失败时返回默认值。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
