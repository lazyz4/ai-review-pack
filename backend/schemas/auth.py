"""认证相关 Pydantic 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """注册请求体。"""

    username: str = Field(..., min_length=2, max_length=32, description="用户名")
    password: str = Field(..., min_length=4, max_length=64, description="密码")


class LoginRequest(BaseModel):
    """登录请求体。"""

    username: str = Field(..., min_length=1, max_length=32, description="用户名")
    password: str = Field(..., min_length=1, max_length=64, description="密码")


class AuthResponse(BaseModel):
    """登录/注册返回体。"""

    token: str
    username: str
    is_demo: bool = False
    expires_at: str


class AuthMeResponse(BaseModel):
    """当前登录用户信息。"""

    username: str
    is_demo: bool = False
