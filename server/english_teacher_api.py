"""HTTP APIs and ElevenLabs webhooks for the British English teacher."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from english_teacher import (
    build_lesson_response,
    extract_student_id,
    get_student,
    save_progress,
)


def _authorize(
    authorization: str | None,
    xi_api_key: str | None,
    x_webhook_secret: str | None,
) -> None:
    secret = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "").strip()
    if not secret:
        return
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    candidates = {token, xi_api_key or "", x_webhook_secret or ""}
    if secret not in candidates:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


def register_english_teacher_routes(app: FastAPI) -> None:
    """Mount student progress APIs and ElevenLabs-compatible webhooks."""

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/students/{student_id}/english-progress")
    async def get_english_progress(student_id: str) -> dict[str, Any]:
        return get_student(student_id)

    @app.post("/api/students/{student_id}/english-progress")
    async def post_english_progress(student_id: str, request: Request) -> dict[str, Any]:
        body = await _json_body(request)
        body["student_id"] = student_id or body.get("student_id")
        return save_progress(body)

    @app.api_route(
        "/webhook/english-teacher/student-lesson",
        methods=["GET", "POST"],
    )
    async def get_student_lesson_webhook(
        request: Request,
        student_id: str | None = Query(default=None),
        authorization: str | None = Header(default=None),
        xi_api_key: str | None = Header(default=None, alias="xi-api-key"),
        x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
    ) -> JSONResponse:
        _authorize(authorization, xi_api_key, x_webhook_secret)
        body = await _json_body(request)
        sid = extract_student_id(body, {"student_id": student_id} if student_id else {})
        return JSONResponse(build_lesson_response(sid))

    @app.post("/webhook/english-teacher/update-progress")
    async def update_progress_webhook(
        request: Request,
        authorization: str | None = Header(default=None),
        xi_api_key: str | None = Header(default=None, alias="xi-api-key"),
        x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
    ) -> JSONResponse:
        _authorize(authorization, xi_api_key, x_webhook_secret)
        body = await _json_body(request)
        nested = body.get("body") if isinstance(body.get("body"), dict) else body
        return JSONResponse(save_progress(nested))


async def _json_body(request: Request) -> dict[str, Any]:
    if request.method in {"GET", "HEAD"}:
        return dict(request.query_params)
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
