"""内存版草案仓库。

MVP 阶段使用带锁的字典保存每个 ``outline_version`` 的生成结果与原始请求，
方便 edit-feedback 与 export 直接引用；后续可无缝替换为数据库实现。
"""

from __future__ import annotations

import threading
from typing import Optional

from backend.schemas.course import GenerateAdvanceRequest, GenerateAdvanceResponse

_lock = threading.Lock()
_drafts: dict[str, GenerateAdvanceResponse] = {}
_requests: dict[str, GenerateAdvanceRequest] = {}


def save_draft(outline_version: str, request: GenerateAdvanceRequest, response: GenerateAdvanceResponse) -> None:
    """保存一个版本对应的请求与生成结果。"""
    with _lock:
        _drafts[outline_version] = response
        _requests[outline_version] = request


def get_draft(outline_version: str) -> Optional[GenerateAdvanceResponse]:
    """按版本号读取生成结果。"""
    with _lock:
        return _drafts.get(outline_version)


def get_request(outline_version: str) -> Optional[GenerateAdvanceRequest]:
    """按版本号读取原始请求。"""
    with _lock:
        return _requests.get(outline_version)
