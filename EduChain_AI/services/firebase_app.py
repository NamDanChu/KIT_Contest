"""Firebase Admin 초기화 (프로세스당 1회, idempotent).

자격 증명 우선순위:
1. 환경 변수 `FIREBASE_SERVICE_ACCOUNT_JSON` (JSON 문자열)
2. 환경 변수 `FIREBASE_CREDENTIALS_PATH` 또는 `GOOGLE_APPLICATION_CREDENTIALS` (파일 경로)
3. Streamlit 실행 시 `st.secrets` 동일 키

Streamlit Cloud에서는 JSON 파일을 두기 어려우므로 `FIREBASE_SERVICE_ACCOUNT_JSON` 권장.
"""

from __future__ import annotations

import json
import os

import firebase_admin
from firebase_admin import credentials


def _credential_from_env_or_secrets() -> credentials.Certificate:
    json_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if json_str:
        return credentials.Certificate(json.loads(json_str))

    path = os.environ.get("FIREBASE_CREDENTIALS_PATH") or os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    if path:
        return credentials.Certificate(path)

    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            sec = st.secrets
            if "FIREBASE_SERVICE_ACCOUNT_JSON" in sec:
                raw = sec["FIREBASE_SERVICE_ACCOUNT_JSON"]
                return credentials.Certificate(json.loads(str(raw)))
            if "FIREBASE_CREDENTIALS_PATH" in sec:
                return credentials.Certificate(str(sec["FIREBASE_CREDENTIALS_PATH"]))
    except Exception:
        pass

    raise RuntimeError(
        "Firebase 자격 증명이 없습니다. "
        "FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_CREDENTIALS_PATH, "
        "GOOGLE_APPLICATION_CREDENTIALS 또는 .streamlit/secrets.toml 을 설정하세요."
    )


def init_firebase() -> None:
    """앱이 없을 때만 초기화."""
    if firebase_admin._apps:
        return
    cred = _credential_from_env_or_secrets()
    firebase_admin.initialize_app(cred)


def get_firestore_client():
    """Firestore 클라이언트 (서비스 계정은 보안 규칙을 우회)."""
    from firebase_admin import firestore

    init_firebase()
    return firestore.client()
