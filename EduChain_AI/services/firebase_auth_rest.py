"""Firebase Auth — Identity Toolkit REST API (이메일·Google id_token → Firebase 세션).

Admin SDK와 별개로, **클라이언트용 Web API 키**가 필요합니다.
콘솔: Firebase → 프로젝트 설정 → 일반 → 웹 API 키 → `FIREBASE_WEB_API_KEY`
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

_AUTH_BASE = "https://identitytoolkit.googleapis.com/v1/accounts"


def _get_web_api_key() -> str:
    try:
        import streamlit as st

        if hasattr(st, "secrets") and "FIREBASE_WEB_API_KEY" in st.secrets:
            return str(st.secrets["FIREBASE_WEB_API_KEY"])
    except Exception:
        pass
    key = os.environ.get("FIREBASE_WEB_API_KEY")
    if not key:
        raise RuntimeError(
            "FIREBASE_WEB_API_KEY 가 없습니다. Firebase 콘솔 웹 API 키를 secrets.toml 또는 환경 변수에 설정하세요."
        )
    return key


def _raise_if_error(resp: requests.Response) -> None:
    if resp.ok:
        return
    try:
        body = resp.json()
        msg = body.get("error", {}).get("message", resp.text)
    except json.JSONDecodeError:
        msg = resp.text
    raise RuntimeError(_firebase_message_ko(str(msg)))


def _firebase_message_ko(msg: str) -> str:
    m = msg.upper()
    if "EMAIL_EXISTS" in m or "EMAIL_ALREADY_EXISTS" in m:
        return "이미 가입된 이메일입니다. 로그인을 시도하세요."
    if "EMAIL_NOT_FOUND" in m:
        return "등록되지 않은 이메일입니다."
    if "INVALID_PASSWORD" in m or "INVALID_LOGIN_CREDENTIALS" in m:
        return "비밀번호가 올바르지 않습니다."
    if "WEAK_PASSWORD" in m:
        return "비밀번호가 너무 짧습니다. 6자 이상으로 설정하세요."
    if "INVALID_IDP_RESPONSE" in m or "INVALID_ID_TOKEN" in m:
        return "Google 인증에 실패했습니다. 다시 시도하세요."
    return f"Firebase 인증 오류: {msg}"


def sign_up_email(email: str, password: str) -> dict[str, Any]:
    """이메일 회원가입. 반환: idToken, localId, email, refreshToken 등."""
    key = _get_web_api_key()
    url = f"{_AUTH_BASE}:signUp?key={key}"
    r = requests.post(
        url,
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=30,
    )
    _raise_if_error(r)
    return r.json()


def sign_in_email(email: str, password: str) -> dict[str, Any]:
    """이메일 로그인."""
    key = _get_web_api_key()
    url = f"{_AUTH_BASE}:signInWithPassword?key={key}"
    r = requests.post(
        url,
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=30,
    )
    _raise_if_error(r)
    return r.json()


def _get_request_uri_for_idp() -> str:
    """Firebase signInWithIdp 의 requestUri — OAuth 리디렉션 URI와 맞추는 것이 안전."""
    try:
        import streamlit as st

        if hasattr(st, "secrets") and "GOOGLE_OAUTH_REDIRECT_URI" in st.secrets:
            return str(st.secrets["GOOGLE_OAUTH_REDIRECT_URI"]).rstrip()
    except Exception:
        pass
    return os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8501/").rstrip()


def sign_in_with_google_id_token(google_id_token: str, request_uri: str | None = None) -> dict[str, Any]:
    """Google OAuth에서 받은 id_token으로 Firebase에 로그인."""
    key = _get_web_api_key()
    url = f"{_AUTH_BASE}:signInWithIdp?key={key}"
    uri = request_uri or _get_request_uri_for_idp()
    post_body = f"id_token={google_id_token}&providerId=google.com"
    r = requests.post(
        url,
        json={
            "postBody": post_body,
            "requestUri": uri,
            "returnIdpCredential": True,
            "returnSecureToken": True,
        },
        timeout=30,
    )
    _raise_if_error(r)
    return r.json()
