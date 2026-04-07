"""Google OAuth 2.0 (웹) — Streamlit에서 링크로 이동 후 콜백으로 code 교환."""

from __future__ import annotations

import os
import secrets as py_secrets
from typing import Any

from google_auth_oauthlib.flow import Flow

_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def _get_redirect_uri() -> str:
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            u = st.secrets.get("GOOGLE_OAUTH_REDIRECT_URI")
            if u:
                return str(u).rstrip()
    except Exception:
        pass
    return os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8501/").rstrip()


def _client_config() -> dict[str, Any]:
    try:
        import streamlit as st

        sec = st.secrets
        cid = str(sec["GOOGLE_OAUTH_CLIENT_ID"])
        csec = str(sec["GOOGLE_OAUTH_CLIENT_SECRET"])
    except Exception:
        cid = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
        csec = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
    if not cid or not csec:
        raise RuntimeError(
            "GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET 을 설정하세요. "
            "Google Cloud 콘솔 → 사용자 인증 정보 → OAuth 2.0 클라이언트 ID(웹 애플리케이션)."
        )
    redir = _get_redirect_uri()
    return {
        "web": {
            "client_id": cid,
            "client_secret": csec,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redir],
        }
    }


def build_flow() -> Flow:
    redir = _get_redirect_uri()
    return Flow.from_client_config(
        _client_config(),
        scopes=_SCOPES,
        redirect_uri=redir,
    )


def create_authorization_url() -> tuple[str, str]:
    """(브라우저로 열 URL, CSRF state)."""
    flow = build_flow()
    state = py_secrets.token_urlsafe(32)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        include_granted_scopes="true",
    )
    return auth_url, state


def exchange_code_for_id_token(code: str) -> str:
    """콜백에서 받은 authorization code → Google id_token."""
    flow = build_flow()
    flow.fetch_token(code=code)
    token = flow.oauth2session.token
    if not isinstance(token, dict):
        raise RuntimeError("OAuth 토큰 응답이 올바르지 않습니다.")
    id_tok = token.get("id_token")
    if not id_tok:
        raise RuntimeError(
            "id_token 을 받지 못했습니다. OAuth 범위에 openid 가 포함되어 있는지 확인하세요."
        )
    return str(id_tok)
