"""Firebase 인증 — 이메일·Google은 `firebase_auth_rest` / `google_oauth_flow` 사용."""

from __future__ import annotations

from .auth_session import clear_auth_session


def sign_out() -> None:
    clear_auth_session()
