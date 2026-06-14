from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def structured_error(
    status_code: int,
    code: str,
    message: str | None = None,
    **extra: Any,
) -> HTTPException:
    detail: dict[str, Any] = {"code": code}
    if message is not None:
        detail["message"] = message
    detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)
