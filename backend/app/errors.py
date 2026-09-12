import logging

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("archaeo")


class BusinessError(Exception):
    def __init__(self, message: str, status_code: int = 409, code: str = "business_rule",
                 details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}


# asyncpg SQLSTATE -> HTTP
_PG_STATUS = {
    "23514": 409,  # check_violation（地层环 / 非开放层位 / 坐标越界 / 跨探方关系）
    "23503": 409,  # foreign_key_violation（被证据引用时 RESTRICT）
    "23505": 409,  # unique_violation
    "42501": 403,  # insufficient_privilege（只追加证据被篡改）
    "23P01": 409,  # exclusion_violation
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessError)
    async def _business(_: Request, exc: BusinessError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "message": exc.message, "details": exc.details},
        )

    @app.exception_handler(asyncpg.PostgresError)
    async def _pg(_: Request, exc: asyncpg.PostgresError) -> JSONResponse:
        sqlstate = exc.sqlstate or ""
        status = _PG_STATUS.get(sqlstate, 400)
        detail = getattr(exc, "detail", None) or str(exc).strip()
        logger.warning("database error %s: %s", sqlstate, detail)
        return JSONResponse(
            status_code=status,
            content={"error": "database_rule_violation", "sqlstate": sqlstate, "message": detail},
        )
