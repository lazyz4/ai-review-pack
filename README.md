# AI 期末复习整合包（多科目 · FastAPI + DeepSeek/OpenAI 兼容 API）

一个真实可用的在线小软件：**选择任意科目**，上传 PPT / PDF / Word / TXT 或粘贴大纲，
AI 分析后生成知识点清单、题型模板、示例题、覆盖率统计与个性化学习计划，并可导出
**Word / PDF / Markdown / JSON**。

默认使用**云端大模型 API（DeepSeek）**，也支持 OpenAI / Kimi / 硅基流动 / 智谱 /
本地 Ollama / 自定义 OpenAI 兼容服务商。

## 功能一览

- 多科目自选：软件测试、数据结构、操作系统、计算机网络、高等数学、大学英语等 + 自定义科目
- 文件上传：`.pptx` / `.pdf` / `.docx` / `.txt` / `.md`（20MB 以内），自动提取文本
- 账号体系：演示账号（demo，密码由部署方在环境变量 `DEMO_PASSWORD` 中设置）直接使用部署方的 DeepSeek Key；注册账号填写自己的 Key（BYOK）
- BYOK 自由选择：DeepSeek / OpenAI / Kimi / 硅基流动 / 智谱 / 本地 Ollama / 自定义
- 结果可微调：修改知识点难度/题型/高频标记后重新评估覆盖率
- 多格式导出：Word / PDF / Markdown / JSON
- 无 Key 且无本地 Ollama 时自动降级为启发式生成，服务不中断

## 目录结构

```text
.
├── backend/
│   ├── main.py                  # FastAPI 主入口（CORS、生命周期、托管前端）
│   ├── api/
│   │   ├── auth.py              # 注册 / 登录 / 当前用户（演示账号 + BYOK）
│   │   ├── generate.py          # 生成（文本 + 文件上传，需登录）
│   │   ├── edit_feedback.py     # 微调并重新评估覆盖率（需登录）
│   │   └── export.py            # 导出 + 下载（需登录）
│   ├── services/
│   │   ├── llm_client.py        # 通用 LLM 客户端（多服务商 + BYOK）
│   │   ├── auth_service.py      # SQLite 账号/会话（PBKDF2 加盐哈希）
│   │   ├── file_parser.py       # PPT/PDF/DOCX/TXT 文本提取
│   │   └── review_pack.py       # 生成管线（LLM + 启发式降级）
│   ├── data/                    # SQLite 数据库（自动创建，已 gitignore）
│   └── requirements.txt
├── frontend/index.html          # 前端单页应用（登录/注册 + 模型设置）
├── outputs/                     # PRD、原型、导出文件
├── Dockerfile                   # 云平台容器部署
├── render.yaml                  # Render 一键部署配置
└── start_server.bat             # 本地双击启动
```

## 快速开始（本地）

```bash
py -m venv .venv
.venv\Scripts\pip install -r backend/requirements.txt
.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 <http://127.0.0.1:8000>，使用演示账号登录：

- 用户名：`demo`
- 密码：环境变量 `DEMO_PASSWORD` 中设置的值（**未设置时不创建演示账号**，请改用注册）

本地没有配置 DeepSeek Key 时，程序自动使用本地 Ollama（需先 `ollama pull qwen2.5:3b`）。

## 云部署（Railway，提供公开网址）

代码已包含 [Dockerfile](Dockerfile) 与 [railway.json](railway.json)，Railway 会自动识别。

方式一（推荐，免绑卡）：打开模板部署入口
**<https://railway.app/new/template?template=https://github.com/lazyz4/ai-review-pack>**

方式二：打开 <https://railway.app/new> → Deploy from GitHub repo → 选择 `lazyz4/ai-review-pack`。

部署步骤：
1. 用 GitHub 账号登录 Railway，点击 Deploy；
2. 构建完成后进入项目 → **Variables**，添加：
   - `MY_DEEPSEEK_KEY` = 你的 `sk-...`（注意：不要在代码/仓库中出现这个 Key）
   - `DEMO_USERNAME` = `demo`（可改）
   - `DEMO_PASSWORD` = 你自己设的密码（可改）
3. 部署成功后，在 **Settings → Networking** 里把公网域名（`*.up.railway.app`）生成出来；
4. 打开该网址即可使用，用演示账号或注册账号登录。

> Railway 免费额度（约 $5/月）一般无需绑卡；若平台要求绑卡，备选方案是
> Hugging Face Spaces（同样免绑卡）或本地部署。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MY_DEEPSEEK_KEY` | 空 | 你自己的 DeepSeek API Key（部署方 Key，用于演示账号；绝不写进代码） |
| `LLM_PROVIDER` | 自动 | 显式指定服务商：deepseek / openai / moonshot / siliconflow / zhipu / ollama / custom |
| `LLM_API_BASE` / `LLM_MODEL` | 按服务商预设 | 自定义服务商地址与模型 |
| `LLM_TIMEOUT` | `600` | 单次生成超时（秒） |
| `DEMO_USERNAME` / `DEMO_PASSWORD` | demo / 由你设置 | 演示账号；**未设置 DEMO_PASSWORD 时不创建演示账号**（代码中无默认密码） |
| `DATABASE_PATH` | `backend/data/users.db` | SQLite 数据库路径 |
| `CORS_ORIGINS` | 本地开发来源 | 逗号分隔的 CORS 白名单 |
| `EXPORT_DIR` | `outputs/exports` | 导出文件目录 |

> 逻辑：存在 `MY_DEEPSEEK_KEY` 时默认服务商为 DeepSeek；没有 Key 时自动使用本地 Ollama，
> 保证本地开发与云端部署都能跑。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | 注册账号（返回 Token） |
| POST | `/api/v1/auth/login` | 登录（演示账号 demo，密码由部署方设置） |
| GET | `/api/v1/auth/me` | 当前用户信息（需 Bearer Token） |
| POST | `/api/v1/generate-advance` | 文本生成复习包（需登录） |
| POST | `/api/v1/generate-advance/upload` | 文件上传生成（需登录） |
| POST | `/api/v1/edit-feedback` | 微调并重新评估（需登录） |
| POST | `/api/v1/export` | 导出文件（需登录） |
| GET | `/api/v1/export/download/{file_name}` | 下载文件（需登录） |
| GET | `/api/v1/health` | 健康检查（无需登录） |

## BYOK 与账号说明

- **演示账号（demo）**：直接使用部署方在环境变量里配置的 DeepSeek Key，方便体验；密码由部署方在 `DEMO_PASSWORD` 中设置，不在前端/仓库中公开；
- **注册账号**：登录后页面弹出 API Key 输入框，Key 保存在该用户自己的浏览器（localStorage），
  生成请求通过 `X-API-Key` 等请求头转发，后端只转发、不存储；
- 云端服务商缺 Key 时明确提示填 Key；Key 无效时返回服务商的具体报错。

## 在线演示（GitHub Pages，仅界面）

<https://lazyz4.github.io/ai-review-pack/>

GitHub Pages 只能托管静态前端，无法运行后端与 DeepSeek 调用；页面会自动检测后端地址。
**完整功能请使用 Render 部署后的公开网址（形如 `*.onrender.com`），或本地 `http://127.0.0.1:8000`。**

## 性能说明

- 云端 DeepSeek：一般 10-60 秒完成一份复习包；
- 本地 CPU 跑 Ollama：约 2-4 分钟（qwen2.5:3b）。
