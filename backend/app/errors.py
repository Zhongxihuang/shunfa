from fastapi import HTTPException, Request


def raise_api_error(status_code: int, error_code: str, message: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"error_code": error_code, "message": message},
    )


def request_id_from(request: Request) -> str | None:
    return request.headers.get("X-Request-ID")


def normalize_http_error(request: Request, exc: HTTPException) -> dict:
    detail = exc.detail
    if isinstance(detail, dict) and "error_code" in detail and "message" in detail:
        payload = {
            "error_code": str(detail["error_code"]),
            "message": str(detail["message"]),
        }
    else:
        message = str(detail)
        payload = {
            "error_code": _default_error_code(exc.status_code, message),
            "message": message,
        }

    request_id = request_id_from(request)
    if request_id:
        payload["request_id"] = request_id
    return payload


def _default_error_code(status_code: int, message: str) -> str:
    if status_code == 401:
        return "invalid_token"
    if status_code == 403:
        return "forbidden"
    if status_code == 404:
        return "not_found"
    if status_code == 409:
        return "conflict"
    if status_code == 422:
        return "validation_error"
    if "DeepSeek API Key" in message:
        return "missing_api_key"
    return "request_failed"
