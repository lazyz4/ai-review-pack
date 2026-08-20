# 软件测试期末复习整合包 — 产品需求文档（PRD）

| 项目 | 内容 |
| --- | --- |
| 版本 | v1.0（草案） |
| 日期 | 2026-08-19 |
| 状态 | MVP 可开发 |
| 适用范围 | 多科目通用（软件测试、数据结构、高等数学等），期末考前自学/复习 |

---

## 1. 产品目标

快速将**教学大纲或复习 PPT** 转化为一个“整合复习包”，包含：

- 知识点要点摘要
- 覆盖率分析（知识点 → 题型的覆盖映射，指标可追踪）
- 题型模板与示例题
- 解析要点
- 个性化学习计划草案
- 可导出的 Word / PDF / Markdown / 导入格式（JSON）

产品支持**多科目自选**（软件测试、数据结构、操作系统、高等数学、大学英语等，
也可自定义科目），以**单科目大纲为核心**，优先保证覆盖率和可用性，便于学生考前直接使用。

## 2. 目标用户与场景

- **目标用户**：大学生，面向各科目期末考试的自学/考前复习人群（不限于软件测试）。
- **使用场景**：
  1. 上传 PPT / 大纲文本
  2. AI 处理，输出整合复习包草案
  3. 用户确认并微调映射 / 难度 / 题型偏好
  4. 导出最终文档

## 3. 核心功能（MVP 必做）

### 3.1 输入端

- 支持上传 PPT Outline，或粘贴文本大纲/教学大纲内容
- 科目自选：下拉选择常见科目（软件测试、数据结构、高等数学等）或自定义科目名称
- 文件上传：支持 .pptx / .pdf / .docx / .txt / .md，自动提取文本后交给 AI 处理
- 课程信息填写：课程名称、课程代码、学期、考试日期、科目标签
- 输出偏好设置：默认 Word，附带 PDF / Markdown / 导入模板（JSON）
- 题型偏好与覆盖优先级（可选项）

### 3.2 AI 处理端（核心逻辑）

- 将大纲解析为 Knowledge Points（知识点）清单（Topic）并排序
- 为每个知识点生成题型模板与覆盖映射，确保覆盖率指标可追踪
- 汇总成整合复习包草案：要点摘要、知识点清单、题型分布、示例题与解析模板、覆盖率统计、初步学习计划草案

### 3.3 用户交互端

- 展示生成结果：摘要、知识点清单、题型分布、示例题、解析模板
- 允许快速修改大纲映射、调整难度、筛选题型、修改每日学习计划等
- 用户确认后进入最终导出

### 3.4 导出端

- 生成可下载的 Word 文档（模板填充后的最终产物）
- 附带导出数据（CSV/JSON）以便导入学习工具

> 技术实现说明：AI 处理端已接入本地 **Ollama**（默认 `qwen2.5:3b`，可自动选择本机模型），
> 真实调用 `/v1/chat/completions` 完成大纲解析、知识点抽取与题目生成；
> Ollama 不可用时自动降级为启发式生成。同时支持 **BYOK 自由选择**：DeepSeek / OpenAI /
> Kimi / 硅基流动 / 智谱 / 自定义 OpenAI 兼容服务商，每个用户填自己的 API Key
>（保存在各自浏览器、仅本次调用转发），互不扣费；部署者可另设服务端 `LLM_API_KEY` 作为默认。

### 3.5 非 MVP 功能（后续迭代）

- 跨科自动对齐
- 学习进度追踪与提醒
- 多人协作
- 更多题解风格模板

## 4. 成功标准与指标

| 指标 | 目标 | 测量方式 |
| --- | --- | --- |
| 覆盖率 | 至少 85% 以上关键知识点有题目覆盖映射（初期目标） | 覆盖率统计：覆盖点数 / 总点数 |
| 题型分布符合度 | 实际题型分布与目标考试常见分布偏差 < 15% | 对比矩阵 |
| 解析质量 | 学生对解析清晰度和正确性自评 ≥ 4/5（5 分制） | 问卷评分 |
| 产出速度 | 从提交大纲到可下载文档总时长 ≤ 5-8 分钟（无异常时） | 端到端计时 |
| 稳定性 | 5-8 名验证用户中留存率 ≥ 75% | 试点统计 |

## 5. 数据与接口概览

### 5.1 核心数据流

```text
PPTOutline / Text
      │
      ▼
    Topic（知识点清单）
      │
      ▼
QuestionTemplate / GeneratedQuestion
      │
      ▼
  CoverageMetrics（覆盖率统计）
      │
      ▼
    StudyPlan（学习计划）
      │
      ▼
  ExportFormat（Word / PDF / Markdown / JSON）
```

### 5.2 数据模型

| 实体 | 关键字段 | 关系 |
| --- | --- | --- |
| User | id、name、role | 1:N Session / AuditLog |
| Course | id、course_id、course_name、semester、exam_date、duration_minutes、outline_source、outline_content、outline_version、created_at、updated_at | 1:N Topic；1:N StudyPlan；1:N CoverageMetrics（按版本） |
| Topic | id、topic_id、course_id、name、summary、chapter_ref、difficulty、is_high_frequency、order_index | N:1 Course；1:N QuestionTemplate |
| QuestionTemplate | id、template_id、topic_id、question_type、stem_template、answer_points、analysis_points、difficulty、count_range | N:1 Topic；1:N GeneratedQuestion |
| GeneratedQuestion | id、question_id、topic_id、question_type、stem、options、answer_points、analysis_points、difficulty | N:1 QuestionTemplate |
| CoverageMetrics | id、course_id、outline_version、total_topics、covered_topics、coverage_rate、threshold、meets_threshold | 按版本 1:N 挂到 Course |
| StudyPlan | id、course_id、outline_version、total_days、start_date、end_date、items | 1:N StudyPlanItem |
| StudyPlanItem | id、day、date、phase、focus_topics、daily_questions、duration_minutes | N:1 StudyPlan |
| ExportFormat | id、course_id、outline_version、format、template、file_path、file_size、download_url | 按版本挂到 Course |
| Session / AuditLog | 会话与审计字段 | 用于追踪与合规 |

### 5.3 API 接口

#### API 1: POST /api/v1/generate-advance

描述：提交大纲文本与元信息，返回生成结果的初步草案。

另有配套端点 **POST /api/v1/generate-advance/upload**（multipart/form-data）：
上传 .pptx / .pdf / .docx / .txt / .md 文件与课程信息，后端自动提取文本后
调用同一生成管线，适合“上传 PPT 直接生成”场景。

请求体示例：

```json
{
  "course_id": "CSE101",
  "course_name": "软件测试",
  "outline_source": "PPT",
  "outline_content": "<原始文本提取后内容>",
  "exam_date": "2026-12-20",
  "duration_minutes": 180,
  "output_formats": ["WORD", "PDF", "Markdown"],
  "topic_preferences": {
    "coverage_priority": "high",
    "difficulty_weight": {"easy": 0.3, "medium": 0.5, "hard": 0.2},
    "preferred_question_types": ["multiple_choice", "short_answer", "case_analysis"]
  }
}
```

返回示例：

```json
{
  "outline_version": "v1.0",
  "summary": "执行摘要……",
  "topics": [],
  "templates": [],
  "generated_questions": [],
  "coverage_metrics": {
    "total_topics": 40,
    "covered_topics": 34,
    "coverage_rate": 0.85,
    "threshold": 0.85,
    "meets_threshold": true
  },
  "study_plan_draft": {},
  "export_options": {}
}
```

#### API 2: POST /api/v1/edit-feedback

描述：用户在结果页对知识点映射、题型、难度等进行修改并重新评估。

请求体示例：

```json
{
  "outline_version": "v1.0",
  "edits": [
    {"topic_id": "T101", "new_difficulty": "hard", "new_question_types": ["coding", "case_analysis"]},
    {"topic_id": "T205", "mark_high_frequency": true}
  ]
}
```

返回：重新生成的覆盖率与更新后的草案（版本号自动递增为 v1.1）。

#### API 3: POST /api/v1/export

描述：导出最终文档，按输出格式生成文件并返回下载链接。

请求体示例：

```json
{
  "outline_version": "v1.0",
  "format": "WORD",
  "template": "default",
  "include_metadata": true
}
```

返回：下载链接、文件大小、文件名。

### 5.4 安全性与版本追踪

- 对含有个别高敏信息的文本进行脱敏，或仅用于教育场景的合规说明
- 每次生成产出设版本号（`outline_version`），并记录 `created_at` / `updated_at` 以便回溯

## 6. 用户体验要点

- 界面简洁，核心聚焦“输入 → 生成 → 确认 → 导出”四步
- 生成结果要有清晰的覆盖率指标与可编辑入口
- 提供快速修改入口，支持点对点微调并重新生成对照覆盖率

## 7. 失败/风险管理

- **风险点**：大纲抽取准确性、题型模板的覆盖率与质量、解析的可读性
- **风控措施**：
  - 建立对照对齐矩阵
  - 固定模板 + 可编辑区
  - 预设常见易错点集合
  - 手动覆盖率阈值提醒
- **回退策略**：若覆盖率低于阈值，提示用户手动调整知识点/难度区间或追加知识点

## 8. 验证与试点计划

- **参与用户**：5-8 名大学生（软件测试相关课程）
- **流程**：上传 PPT 大纲 → AI 生成整合包 → 用户确认修改 → 导出 Word
- **指标**：覆盖率、题型分布、解析清晰度、生成时长、用户体验
- **失败标准**：覆盖率持续 < 70% 的参与比例较高，或解析质量评分低

## 9. 风险与应对要点

- 建立质量评估基线（教师/领域专家对照）
- 多轮提示 + 模板策略
- 快速编辑区
- 阈值设定与回退逻辑

## 10. 交付物清单

- PRD 摘要：目标、用户、核心场景、成功标准、风险
- 数据模型与接口说明：实体字段清单、API 端点与请求/返回示例、版本控制字段
- 前端原型草图文本描述：页面结构、组件、字段标签、按钮文案、帮助文本
- 原型导出策略：Word 模板字段映射表、可导出格式模板文本
- 验证方案：5-8 名学生的验证用例、评价指标、失败标准
- 风险与缓解计划

---

## 附录 A：文本化原型草图

### A.1 主页面框架

```text
┌──────────────────────────────────────────────────────────────┐
│ 顶部导航：软件测试期末复习整合包   [输入大纲] [生成结果] [导出] [帮助] │
├──────────────────────────────┬───────────────────────────────┤
│ 左侧输入区                    │ 右侧预览区/结果摘要             │
│  · 上传 PPT Outline（按钮）    │  · 执行摘要文本                │
│  · 粘贴文本 Outline（文本框）   │  · 覆盖率预估（只读）           │
│  · 课程名称/代码/学期/考试日期   │    - 大纲点总数               │
│  · 科目：软件测试              │    - 覆盖点数                 │
│  · 输出偏好：Word(默认)/PDF/    │    - 覆盖率百分比             │
│    Markdown/导入模板           │  · [Start AI Generate]       │
│  · 题型偏好与覆盖优先级（折叠）   │  · 处理状态指示器（进度条）      │
└──────────────────────────────┴───────────────────────────────┘
```

### A.2 结果页分块

```text
┌──────────────────────────────────────────────────────────────┐
│ 结果标题 + 版本信息（outline_version v1.0）                     │
├──────────────────────────────────────────────────────────────┤
│ 页面 1：产出摘要（目标/知识点总览/题型分布/初步练习计划）            │
│ 页面 2：知识点清单（表格：ID/名称/要点摘要/章节/难度/是否高频）      │
│ 页面 3：题型模板与覆盖映射（模板表 + 题目生成模板表）              │
│ 页面 4：示例题（3-5 道：题干/选项/解析要点）                     │
│ 页面 5：覆盖率与完整性评估（柱状/圆环图 + 题型分布对比）           │
│ 页面 6：个性化学习计划草案（日期/阶段/目标知识点/每日题量/时长）     │
│ 页面 7：导出选项（格式选择/模板选择/下载按钮）                    │
├──────────────────────────────────────────────────────────────┤
│ 用户互动区：每个知识点/题型可展开微编辑（名称/要点/难度/题型），      │
│ 修改后重新评估覆盖率                                             │
└──────────────────────────────────────────────────────────────┘
```

### A.3 交互流程简述

1. Step 1：用户输入大纲信息（上传/粘贴 + 元信息）
2. Step 2：点击“生成”触发后端生成草案
3. Step 3：结果页面出现，用户查看并在必要处修改映射/难度/题型
4. Step 4：用户确认后，点击“导出”完成 Word/PDF 等格式的下载
