"""Firebase Auth Admin — 이메일 계정 직접 생성(운영자용)."""

from __future__ import annotations

from firebase_admin import auth as fb_auth

from .firebase_app import init_firebase


def create_email_password_user(
    email: str,
    password: str,
    *,
    display_name: str = "",
) -> str:
    """이메일·비밀번호로 Firebase Auth 사용자 생성. 반환: uid."""
    init_firebase()
    kwargs: dict[str, str] = {"email": email.strip(), "password": password}
    if display_name.strip():
        kwargs["display_name"] = display_name.strip()
    try:
        rec = fb_auth.create_user(**kwargs)
    except Exception as e:
        msg = str(e).lower()
        if "email" in msg and ("exists" in msg or "already" in msg):
            raise RuntimeError("이미 사용 중인 이메일입니다.") from e
        raise RuntimeError(str(e)) from e
    return str(rec.uid)


def update_auth_user(
    uid: str,
    *,
    password: str | None = None,
    display_name: str | None = None,
) -> None:
    """Firebase Auth 사용자 — 비밀번호·표시 이름(닉네임) 갱신. 비어 있으면 해당 필드는 건너뜀."""
    init_firebase()
    kwargs: dict[str, str] = {}
    if password is not None and str(password).strip():
        pw = str(password).strip()
        if len(pw) < 6:
            raise RuntimeError("비밀번호는 6자 이상이어야 합니다.")
        kwargs["password"] = pw
    if display_name is not None:
        kwargs["display_name"] = str(display_name).strip()
    if not kwargs:
        return
    try:
        fb_auth.update_user(uid, **kwargs)
    except Exception as e:
        raise RuntimeError(str(e)) from e


def delete_auth_user(uid: str) -> None:
    """Firebase Authentication 사용자 삭제."""
    init_firebase()
    try:
        fb_auth.delete_user(uid)
    except Exception as e:
        em = str(e).lower()
        if "user_not_found" in em or "not found" in em:
            return
        raise RuntimeError(str(e)) from e
