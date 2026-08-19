"""Ollama 本地大模型客户端。

通过 Ollama 提供的 OpenAI 兼容接口（``/v1/chat/completions``）调用本地模型，
无需访问外网即可完成大纲解析、知识点抽取与题目生成。

默认模型为 ``qwen2.5:3b``（中文效果好、CPU 上速度快）；若配置的模型未安装，会自动回退到本机已安装的
第一个可用模型（优先选择 qwen/glm/deepseek 等中文表现更好的模型）。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("review-pack.ollama")

DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_MODEL = "qwen2.5:3b"
PREFERRED_MODEL_KEYWORDS = ("qwen", "glm", "deepseek", "yi", "chat", "llama")


class OllamaClient:
    """Ollama OpenAI 兼容接口的轻量异步封装。"""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL, timeout: float = 300.0) -> None:
        """初始化客户端。

        Args:
            base_url: Ollama OpenAI 兼容端点，例如 ``http://127.0.0.1:11434/v1``。
            model: 首选本地模型名，例如 ``qwen2.5:3b``。
            timeout: 单次请求超时（秒）。
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.effective_model: str | None = None

    async def list_models(self) -> list[str]:
        """列出本机 Ollama 已安装的模型。"""
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.base_url}/models")
            response.raise_for_status()
            data = response.json()
        models: list[str] = []
        for item in data.get("data", []):
            name = item.get("id") or item.get("model")
            if name:
                models.append(str(name))
        return models

    async def resolve_effective_model(self) -> str:
        """确定实际使用的模型：配置值可用则优先，否则自动挑选本机模型。"""
        try:
            models = await self.list_models()
        except Exception:  # noqa: BLE001 - 查询失败时直接使用配置值
            logger.warning("无法查询 Ollama 模型列表，将直接使用配置模型 %s", self.model)
            return self.model
        if not models:
            return self.model
        if self.model in models:
            return self.model

        def rank(name: str) -> int:
            lowered = name.lower()
            for index, keyword in enumerate(PREFERRED_MODEL_KEYWORDS):
                if keyword in lowered:
                    return index
            return len(PREFERRED_MODEL_KEYWORDS)

        chosen = min(models, key=rank)
        logger.warning(
            "配置模型 %s 未安装，已自动选用本机模型 %s（本机可用：%s）",
            self.model,
            chosen,
            "、".join(models),
        )
        return chosen

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.4, max_tokens: int = 4096) -> str:
        """发送聊天补全请求并返回助手文本。"""
        import httpx

        model = self.effective_model or self.model
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Ollama 返回结构异常: {data}") from exc

    async def is_available(self) -> bool:
        """探测 Ollama 服务是否可用。"""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.base_url}/models")
            return response.status_code == 200
        except httpx.HTTPError:
            return False
