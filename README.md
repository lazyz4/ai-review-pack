# AI 期末复习整合包（多科目 · FastAPI + Ollama）

一个真实可用的本地小软件：**选择任意科目**，上传 PPT / PDF / Word / TXT 或粘贴大纲，
程序会**真实调用本地 Ollama 模型**分析大纲、生成知识点清单、题型模板、示例题、
覆盖率统计与个性化学习计划，并可导出 **Word / PDF / Markdown / JSON**。

## 功能一览

- 多科目自选：软件测试、数据结构、操作系统、计算机网络、高等数学、大学英语等 + 自定义科目
- 文件上传：`.pptx` / `.pdf` / `.docx` / `.txt` / `.md`（20MB 以内），自动提取文本
- 真实 Ollama 生成：默认 `qwen2.5:3b`（中文好、CPU 快），模型缺失时自动选择本机可用模型
- BYOK 自由选择：页面可切换 DeepSeek / OpenAI / Kimi / 硅基流动 / 智谱 / 本地 Ollama / 自定义，
  每个用户填自己的 API Key（只存自己浏览器、仅本次调用），互不扣费
- 结果可微调：修改知识点难度/题型/高频标记后调用 `edit-feedback` 重新评估覆盖率
- 多格式导出：Word / PDF / Markdown / JSON，支持下载
- Ollama 不可用时自动降级为启发式生成，服务不中断

## 目录结构

```text
.
├── backend/
│   ├── main.py                  # FastAPI 主入口（CORS、生命周期、托管前端）
│   ├── api/
│   │   ├── generate.py          # POST /api/v1/generate-advance（文本 + 文件上传）
│   │   ├── edit_feedback.py     # POST /api/v1/edit-feedback
│   │   └── export.py            # POST /api/v1/export + 文件下载
│   ├── models/course.py         # Course / Topic ORM 模型
│   ├── schemas/course.py        # Pydantic 请求/响应模型
│   ├── services/
│   │   ├── llm_client.py        # 通用 LLM 客户端（多服务商 + BYOK）
│   │   ├── file_parser.py       # PPT/PDF/DOCX/TXT 文本提取
│   │   └── review_pack.py       # 生成管线（LLM + 启发式降级）
│   ├── store.py                 # 内存草案仓库（按 outline_version）
│   └── requirements.txt
├── frontend/index.html          # 真实前端单页应用（由 FastAPI 托管）
├── outputs/
│   ├── PRD.md                   # 产品需求文档
│   ├── prototype.html           # 交互原型（设计稿）
│   └── exports/                 # 导出的复习包文件
└── start_server.bat             # 双击启动脚本
```

## 快速开始

### 1. 安装依赖（首次）

```bash
py -m venv .venv
.venv\Scripts\pip install -r backend/requirements.txt
```

### 2. 准备 Ollama 模型（推荐中文模型）

```bash
ollama pull qwen2.5:3b
ollama serve
```

如果本机已有其他模型（如 llama3.1:8b），程序会自动选用；中文内容建议优先 qwen 系列。

### 3. 启动

```bash
.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

或直接双击 `start_server.bat`，然后浏览器打开：

**<http://127.0.0.1:8000>**（前端界面）或 <http://127.0.0.1:8000/docs>（API 文档）

> 若 8000 端口被占用，可改用 `--port 8001`，前端会自动跟随同一端口访问。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama` | 服务端默认服务商：ollama / deepseek / openai / moonshot / siliconflow / zhipu / custom |
| `LLM_API_KEY` | 空 | 服务端默认 API Key（你自己的 Key；云端部署后仍建议让用户填自己的 Key） |
| `LLM_API_BASE` | 按服务商预设 | 自定义服务商的 Base URL（custom 时必填） |
| `LLM_MODEL` | 按服务商预设 | 默认模型名 |
| `LLM_TIMEOUT` | `600` | 单次生成超时（秒） |
| `CORS_ORIGINS` | `http://localhost:5173,...` | 逗号分隔的 CORS 白名单 |
| `EXPORT_DIR` | `outputs/exports` | 导出文件目录 |

## BYOK：每个用户用自己的 API Key

页面“模型设置”里选择服务商并填写自己的 API Key（保存在浏览器 localStorage），
生成请求会通过请求头携带（`X-LLM-Provider` / `X-API-Key` / `X-LLM-Base-URL` / `X-LLM-Model`）。
后端**只转发、不存储**，优先使用请求带来的 Key；没带 Key 时使用服务端 `LLM_API_KEY`；
都没配且选了云端服务商时，会明确提示填 Key，而不是悄悄降级。

因此：
- 你（部署者）本地使用：页面填自己的 Key 或服务端设 `LLM_API_KEY`，都可以；
- 别人使用你的部署：他们必须填自己的 Key，花他们自己的额度，你的余额不受影响；
- 本地 Ollama：完全免费、无需 Key，但只在运行后端的电脑上可用。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/generate-advance` | 提交大纲 JSON，调用 Ollama 生成复习包 |
| POST | `/api/v1/generate-advance/upload` | multipart 上传文件 + 课程信息，生成复习包 |
| POST | `/api/v1/edit-feedback` | 微调知识点并重新评估覆盖率（版本自动 +0.1） |
| POST | `/api/v1/export` | 按格式导出（WORD/PDF/MARKDOWN/JSON） |
| GET | `/api/v1/export/download/{file_name}` | 下载导出文件 |
| GET | `/api/v1/health` | 健康检查（含 Ollama 可用性与实际模型） |

## 性能说明（重要）

- 本机为纯 CPU 推理：qwen2.5:3b 生成一份复习包约 **2-4 分钟**，llama3.1:8b 会更慢。
- 生成逻辑已做精简约束（知识点 ≤ 15、示例题 3 道、单次输出 ≤ 2048 tokens）。
- 若希望更快，可 `ollama pull qwen2.5:1.5b` 并用环境变量 `OLLAMA_MODEL=qwen2.5:1.5b` 指定；
  若追求更高质量且机器性能较好，可 `ollama pull qwen2.5:7b`。

## 技术要点

- **多科目**：请求体新增 `subject` / `semester` 字段，LLM 提示词按科目标签适配术语。
- **文件解析**：`file_parser.py` 支持 PPTX（文本框+表格）、PDF（pypdf）、DOCX（python-docx）、TXT/MD。
- **降级策略**：本地 Ollama 两次生成失败或不可用时，自动返回启发式生成结果；云端服务商出错时如实报错（如 Key 无效）。
- **版本追踪**：`outline_version` 每次微调递增（v1.0 → v1.1），草案保存在内存仓库。

## 交付物

- [PRD（产品需求文档）](outputs/PRD.md)
- [交互原型（设计稿）](outputs/prototype.html)
- [真实前端应用](frontend/index.html)

## 在线演示（GitHub Pages）

网站已部署到：**https://lazyz4.github.io/ai-review-pack/**

说明：GitHub Pages 只能托管静态前端，无法运行 Ollama（本地大模型）。页面加载时会自动检测
本地后端（`http://127.0.0.1:8000`）并提示连接状态。由于浏览器安全策略（HTTPS 页面访问本地
HTTP 服务可能被拦截），**真正生成复习包请直接打开 <http://127.0.0.1:8000> 使用**；
在线链接适合分享界面演示、查看代码与 PRD。BYOK 的 API Key 也是由你的后端转发给大模型服务商
（浏览器无法直接调用 DeepSeek 等 API），所以**完整功能始终需要一个可达的后端实例**
（本地运行，或部署到云服务器/免费容器平台）。
