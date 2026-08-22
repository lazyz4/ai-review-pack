"""通用 LLM 客户端（OpenAI 兼容）。

支持任意 OpenAI 兼容服务商：DeepSeek、OpenAI、Moonshot Kimi、硅基流动、
智谱 GLM、本地 Ollama，以及自定义 base_url + 模型名。

BYOK 设计：每个请求都可以通过请求头携带用户自己的 API Key
（``X-API-Key`` / ``X-LLM-Provider`` / ``X-LLM-Base-URL`` / ``X-LLM-Model``），
后端只转发、不存储；未携带时使用服务端环境变量配置的 Key；本地 Ollama 不需要 Key。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("review-pack.llm")

PROVIDERS: dict[str, dict[str, str]] = {
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "moonshot": {"label": "Moonshot Kimi", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "siliconflow": {"label": "硅基流动", "base_url": "https://api.siliconflow.cn/v1", "model": "Qwen/Qwen2.5-7B-Instruct"},
    "zhipu": {"label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    "ollama": {"label": "本地 Ollama", "base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5:3b"},
}

DEFAULT_PROVIDER = "ollama"
PREFERRED_MODEL_KEYWORDS = ("qwen", "glm", "deepseek", "yi", "chat", "llama")


class LLMError(Exception):
    """LLM 调用错误，携带建议返回给前端的 HTTP 状态码。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMClient:
    """任意 OpenAI 兼容 LLM 服务商的异步客户端。"""

    def __init__(
        self,
        provider: str = DEFAULT_PROVIDER,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        timeout: float = 600.0,
    ) -> None:
        provider = (provider or DEFAULT_PROVIDER).lower()
        preset = PROVIDERS.get(provider, PROVIDERS[DEFAULT_PROVIDER])
        self.provider = provider
        self.api_key = api_key
        self.base_url = (base_url or preset["base_url"]).rstrip("/")
        self.model = model or preset["model"]
        self.timeout = timeout
        self.effective_model: str | None = None

    def _headers(self, api_key: str) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def effective_api_key(self, provider: str = "", api_key: str = "") -> str:
        """BYOK：请求级 Key 优先；未提供时仅当所选服务商与服务端一致才回退到服务端 Key。

        避免把服务端 DeepSeek Key 误发给 OpenAI / Kimi 等其他服务商。
        """
        key = (api_key or "").strip()
        if key:
            return key
        if (provider or self.provider or "").lower() == (self.provider or "").lower():
            return self.api_key or ""
        return ""

    async def list_models(self, api_key: str = "", base_url: str = "") -> list[str]:
        """列出服务商可用模型。"""
        import httpx

        base = (base_url or self.base_url).rstrip("/")
        key = api_key or self.api_key
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{base}/models", headers=headers)
            response.raise_for_status()
            data = response.json()
        models: list[str] = []
        for item in data.get("data", []):
            name = item.get("id") or item.get("model")
            if name:
                models.append(str(name))
        return models

    async def resolve_effective_model(self) -> str:
        """本地 Ollama：配置的模型缺失时自动挑选本机已安装模型。"""
        if self.provider != "ollama":
            return self.model
        try:
            models = await self.list_models()
        except Exception:  # noqa: BLE001 - 查询失败时使用配置值
            return self.model
        if not models or self.model in models:
            return self.model

        def rank(name: str) -> int:
            lowered = name.lower()
            for index, keyword in enumerate(PREFERRED_MODEL_KEYWORDS):
                if keyword in lowered:
                    return index
            return len(PREFERRED_MODEL_KEYWORDS)

        chosen = min(models, key=rank)
        logger.warning("本地模型 %s 未安装，自动选用 %s（可用：%s）", self.model, chosen, "、".join(models))
        return chosen

    async def verify(
        self,
        provider: str = "",
        api_key: str = "",
        base_url: str = "",
        model: str = "",
    ) -> tuple[bool, str, str]:
        """探测服务是否可用，返回 (是否可用, 说明文字, 实际模型名)。"""
        import httpx

        provider = (provider or self.provider or DEFAULT_PROVIDER).lower()
        preset = PROVIDERS.get(provider)
        key = self.effective_api_key(provider, api_key)
        base = (base_url or (preset["base_url"] if preset else "") or self.base_url).rstrip("/")
        mdl = model or (preset["model"] if preset else "") or self.model
        if provider not in PROVIDERS and provider != "custom":
            return False, f"未知服务商：{provider}", mdl
        if provider != "ollama" and provider != "custom" and not key:
            return False, "缺少 API Key（请在页面“模型设置”中填写）", mdl
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{base}/models", headers=headers)
        except httpx.HTTPError as exc:
            return False, f"无法连接：{exc}", mdl
        if response.status_code == 200:
            return True, "已连接", mdl
        if response.status_code in (401, 403):
            return False, "API Key 无效（HTTP " + str(response.status_code) + "）", mdl
        return False, f"连接失败（HTTP {response.status_code}）", mdl

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        provider: str = "",
        api_key: str = "",
        base_url: str = "",
        model: str = "",
    ) -> str:
        """发送聊天补全请求并返回助手文本（BYOK：请求级 Key 优先）。"""
        import httpx

        provider = (provider or self.provider or DEFAULT_PROVIDER).lower()
        preset = PROVIDERS.get(provider)
        key = self.effective_api_key(provider, api_key)
        base = (base_url or (preset["base_url"] if preset else "") or self.base_url).rstrip("/")
        mdl = model or (preset["model"] if preset else "") or self.model
        if provider != "ollama" and provider != "custom" and not key:
            raise LLMError("缺少 API Key：请在“模型设置”中填写你自己的 Key（每个用户用各自的 Key，互不影响）")
        if provider == "custom" and not base_url:
            raise LLMError("自定义服务商需要填写 Base URL（例如 https://api.example.com/v1）")
        payload: dict[str, Any] = {
            "model": mdl,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = self._headers(key)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{base}/chat/completions", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"无法连接模型服务：{exc}", status_code=502) from exc
        if response.status_code >= 400:
            detail = _error_detail(response)
            code = response.status_code if response.status_code >= 500 else 400
            raise LLMError(f"模型服务返回错误（HTTP {response.status_code}）：{detail}", status_code=code)
        data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"模型返回结构异常：{str(data)[:200]}") from exc


def _error_detail(response: Any) -> str:
    """尽量从错误响应中提取人类可读的说明（不包含密钥）。"""
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            message = error.get("message", "")
        else:
            message = str(error or "")
        return str(message)[:200] or "未知错误"
    except Exception:  # noqa: BLE001
        return "未知错误"


def overrides_from_headers(headers) -> dict[str, str]:
    """从请求头解析 BYOK 覆盖项（provider / api_key / base_url / model）。"""
    return {
        "provider": (headers.get("x-llm-provider") or "").strip(),
        "api_key": (headers.get("x-api-key") or "").strip(),
        "base_url": (headers.get("x-llm-base-url") or "").strip(),
        "model": (headers.get("x-llm-model") or "").strip(),
    }
