"""认证路由：注册 / 登录 / 当前用户。

演示账号（默认 demo / demo123）直接使用服务端环境变量中的 DeepSeek Key；
注册账号在前端填写自己的 API Key（BYOK），按请求头发送、后端不存储。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from backend.schemas.auth import AuthMeResponse, AuthResponse, LoginRequest, RegisterRequest
from backend.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def require_user(authorization: str | None = Header(None)) -> dict:
    """FastAPI 依赖：校验 Bearer Token，返回当前用户信息。"""
    token = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else ""
    user = auth_service.get_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录（演示账号：demo / demo123）")
    return user


@router.post("/register", response_model=AuthResponse, summary="注册新账号")
async def register(payload: RegisterRequest) -> AuthResponse:
    """注册账号并自动登录（注册用户需在页面填写自己的 API Key）。"""
    try:
        result = auth_service.register(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuthResponse(**result)


@router.post("/login", response_model=AuthResponse, summary="登录（含演示账号）")
async def login(payload: LoginRequest) -> AuthResponse:
    """登录并返回会话 Token。"""
    try:
        result = auth_service.login(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuthResponse(**result)


@router.get("/me", response_model=AuthMeResponse, summary="当前登录用户")
async def me(user: dict = Depends(require_user)) -> AuthMeResponse:
    """返回当前登录用户信息（用于前端判断演示/注册账号）。"""
    return AuthMeResponse(username=user["username"], is_demo=user["is_demo"])
