"""Firebase 웹 앱 설정 (JS SDK `firebaseConfig` 와 동일한 키).

콘솔: Firebase → 프로젝트 설정 → 일반 → 내 앱(웹)에서 복사한 값을
`.streamlit/secrets.toml` 또는 환경 변수에 넣습니다.

`apiKey` 는 기존 `FIREBASE_WEB_API_KEY` 와 동일합니다.
"""

from __future__ import annotations

import json
import os
from typing import Any


def _from_secrets_or_env(key: str) -> str | None:
    try:
        import streamlit as st

        if hasattr(st, "secrets") and key in st.secrets:
            v = st.secrets[key]
            return str(v).strip() if v is not None else None
    except Exception:
        pass
    return os.environ.get(key)


def get_firebase_web_config(*, include_measurement_id: bool = True) -> dict[str, str]:
    """Streamlit 커스텀 컴포넌트·문서화용 dict. Analytics용 measurementId 는 선택."""
    api_key = _from_secrets_or_env("FIREBASE_WEB_API_KEY")
    if not api_key:
        raise RuntimeError(
            "FIREBASE_WEB_API_KEY 가 없습니다. Firebase 콘솔 웹 앱 설정의 apiKey 와 같습니다."
        )

    required = {
        "apiKey": api_key,
        "authDomain": _from_secrets_or_env("FIREBASE_AUTH_DOMAIN"),
        "projectId": _from_secrets_or_env("FIREBASE_PROJECT_ID"),
        "storageBucket": _from_secrets_or_env("FIREBASE_STORAGE_BUCKET"),
        "messagingSenderId": _from_secrets_or_env("FIREBASE_MESSAGING_SENDER_ID"),
        "appId": _from_secrets_or_env("FIREBASE_APP_ID"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError(
            "Firebase 웹 설정이 불완전합니다. secrets 에 다음을 채우세요: "
            + ", ".join(missing)
        )

    out: dict[str, str] = {k: str(v) for k, v in required.items() if v}
    if include_measurement_id:
        mid = _from_secrets_or_env("FIREBASE_MEASUREMENT_ID")
        if mid:
            out["measurementId"] = str(mid)
    return out


def get_firebase_web_config_json(*, indent: int | None = 2) -> str:
    """JSON 문자열 (HTML/컴포넌트에 삽입할 때)."""
    cfg = get_firebase_web_config()
    return json.dumps(cfg, ensure_ascii=False, indent=indent)


def try_get_firebase_web_config() -> dict[str, Any] | None:
    """선택 로드. 키가 없으면 None (대시보드에서 설정 안내용)."""
    try:
        return get_firebase_web_config()
    except RuntimeError:
        return None
