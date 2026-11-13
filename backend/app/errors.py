import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class NotFound(AppError):
    def __init__(self, message="리소스를 찾을 수 없습니다."):
        super().__init__(404, "not_found", message)


class UpstreamError(AppError):
    def __init__(self, message="Steam 서버에서 응답을 받지 못했습니다.", status=502, code="steam_unavailable"):
        super().__init__(status, code, message)


def _body(code: str, message: str, details=None):
    return {"error": {"code": code, "message": message, "details": details}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app(_: Request, e: AppError):
        return JSONResponse(_body(e.code, e.message), status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, e: RequestValidationError):
        details = [{"loc": [str(p) for p in x["loc"]], "msg": x["msg"]} for x in e.errors()]
        return JSONResponse(_body("invalid_request", "요청 값이 올바르지 않습니다.", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException):
        return JSONResponse(_body("http_error", str(e.detail)), status_code=e.status_code)

    @app.exception_handler(Exception)
    async def _any(_: Request, e: Exception):
        logging.getLogger("app").exception("unhandled error")
        return JSONResponse(_body("internal_error", "서버 내부 오류가 발생했습니다."), status_code=500)
