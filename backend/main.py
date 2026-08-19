"""FastAPI 主入口。

- 导入所有路由（generate / edit-feedback / export）
- 配置 CORS
- 配置应用生命周期：启动时初始化共享的 Ollama 客户端并自动选择可用模型
- 托管真实前端页面（frontend/index.html）
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import edit_feedback, export, generate
from backend.services.ollama_client import OllamaClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("review-pack.main")

PROJECT_NAME = "软件测试期末复习整合包 API"
PROJECT_DESCRIPTION = (
    "将教学大纲或复习 PPT 转化为整合复习包的 FastAPI 服务："
    "知识点解析、题型模板、覆盖率评估、学习计划与多格式导出。"
)
API_VERSION = "v1"
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _cors_origins() -> list[str]:
    """从环境变量读取 CORS 白名单，缺省时返回本地开发常用来源。"""
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if not raw:
        return DEFAULT_CORS_ORIGINS
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> FastAPI:
    """构建并配置 FastAPI 应用。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """启动时创建共享 Ollama 客户端，关闭时释放资源。"""
        llm = OllamaClient(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
            model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
            timeout=float(os.getenv("OLLAMA_TIMEOUT", "600")),
        )
        llm.effective_model = await llm.resolve_effective_model()
        app.state.llm = llm
        logger.info("Ollama 客户端已就绪：model=%s base_url=%s", llm.effective_model, llm.base_url)
        yield
        logger.info("应用正在关闭。")

    app = FastAPI(
        title=PROJECT_NAME,
        description=PROJECT_DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_origin_regex=r"https://.*\.github\.io",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(generate.router, prefix=f"/api/{API_VERSION}")
    app.include_router(edit_feedback.router, prefix=f"/api/{API_VERSION}")
    app.include_router(export.router, prefix=f"/api/{API_VERSION}")

    @app.get(f"/api/{API_VERSION}/health", tags=["system"])
    async def health() -> dict[str, str | bool]:
        """健康检查：返回服务状态、Ollama 可用性与实际使用模型。"""
        llm: OllamaClient = app.state.llm
        available = await llm.is_available()
        return {"status": "ok", "ollama_available": available, "model": llm.effective_model or llm.model}

    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
