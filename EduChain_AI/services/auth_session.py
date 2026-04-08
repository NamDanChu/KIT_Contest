"""로그인 성공 후 session_state·Firestore 프로필 동기화."""

from __future__ import annotations

import os
from typing import Any

import firebase_admin.auth as fb_auth

from .firebase_app import init_firebase
from .firestore_repo import (
    count_all_users,
    count_students_in_org,
    find_org_and_role_by_invite_code,
    get_organization,
    get_user,
    get_user_role,
    submit_org_join_request,
    upsert_user,
)
from .session_keys import (
    AUTH_DISPLAY_NAME,
    AUTH_EMAIL,
    AUTH_ID_TOKEN,
    AUTH_ORG_ID,
    AUTH_ORG_NAME,
    AUTH_REFRESH_TOKEN,
    AUTH_ROLE,
    AUTH_UID,
    AUTH_VIEW,
    MGMT_SELECTED_ORG_ID,
    MGMT_VIEW_MODE,
    MGMT_DETAIL_TAB,
    TEACHER_SELECTED_CATEGORY_ID,
    TEACHER_SELECTED_SUB_ITEM_ID,
    TEACHER_VIEW_TAB,
    TEACHER_LESSON_FINGERPRINT,
)


def _default_org_id() -> str:
    try:
        import streamlit as st

        if hasattr(st, "secrets") and "DEFAULT_ORG_ID" in st.secrets:
            return str(st.secrets["DEFAULT_ORG_ID"])
    except Exception:
        pass
    return os.environ.get("DEFAULT_ORG_ID", "default-org")


def _session_org_id_from_existing(existing: dict[str, Any]) -> str:
    raw = existing.get("org_id")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return ""
    return str(raw)


def apply_firebase_rest_result(
    data: dict[str, Any],
    *,
    signup_profile: dict[str, str] | None = None,
) -> None:
    """Identity Toolkit 응답 반영. signup_profile: 이메일 회원가입 시 이름·기업명."""
    import streamlit as st

    init_firebase()
    id_token = data.get("idToken")
    if not id_token:
        raise RuntimeError("idToken 이 없습니다.")

    # iat/nbf 검증 시 로컬·서버 시계가 1~2초 어긋나면 "Token used too early" 발생 → SDK 시계 허용치 사용(최대 60초)
    try:
        decoded = fb_auth.verify_id_token(id_token, clock_skew_seconds=60)
    except TypeError:
        decoded = fb_auth.verify_id_token(id_token)
    uid = decoded["uid"]
    email = decoded.get("email") or data.get("email") or ""

    st.session_state[AUTH_UID] = uid
    st.session_state[AUTH_EMAIL] = email
    st.session_state[AUTH_ID_TOKEN] = id_token
    if data.get("refreshToken"):
        st.session_state[AUTH_REFRESH_TOKEN] = str(data["refreshToken"])

    existing = get_user(uid)
    if existing:
        org_id = _session_org_id_from_existing(existing)
        role = str(existing.get("role") or get_user_role(uid) or "Student")
        display_name = str(existing.get("display_name") or email.split("@")[0])
        st.session_state[AUTH_DISPLAY_NAME] = display_name
        st.session_state[AUTH_ROLE] = role
        st.session_state[AUTH_ORG_ID] = org_id
        org = get_organization(org_id) if org_id else None
        st.session_state[AUTH_ORG_NAME] = (
            str(org.get("org_name")) if org else ""
        )
        st.session_state.pop("oauth_url", None)
        return

    # 신규 사용자 — 초대 코드 가입(교사/학생)
    if signup_profile and signup_profile.get("invite_org_id"):
        inv_org = str(signup_profile["invite_org_id"]).strip()
        inv_role = str(signup_profile.get("invite_role") or "Student").strip()
        if inv_role not in ("Teacher", "Student"):
            raise RuntimeError("유효하지 않은 초대 역할입니다.")
        display_name = (signup_profile.get("display_name") or "").strip() or (
            email.split("@")[0] if email else "사용자"
        )
        org = get_organization(inv_org)
        if not org:
            raise RuntimeError("초대가 유효하지 않거나 기업을 찾을 수 없습니다.")
        if inv_role == "Student":
            max_slots = int(org.get("max_slots") or 0)
            if count_students_in_org(inv_org) >= max_slots:
                raise RuntimeError(
                    "학생 슬롯이 가득 찼습니다. 운영자에게 문의하세요."
                )
        upsert_user(uid, email, "User", None, display_name=display_name)
        submit_org_join_request(
            uid, email, display_name, inv_org, inv_role
        )
        st.session_state[AUTH_ROLE] = "User"
        st.session_state[AUTH_ORG_ID] = ""
        st.session_state[AUTH_DISPLAY_NAME] = display_name
        st.session_state[AUTH_ORG_NAME] = ""
        st.session_state.pop("oauth_url", None)
        return

    # 신규 사용자 — 이메일 회원가입: 운영자 / 유저 선택 (기업명 없이)
    if signup_profile and signup_profile.get("signup_choice") in ("operator", "user"):
        display_name = (signup_profile.get("display_name") or "").strip() or (
            email.split("@")[0] if email else "사용자"
        )
        choice = str(signup_profile.get("signup_choice"))
        if choice == "operator":
            upsert_user(uid, email, "Operator", None, display_name=display_name)
            st.session_state[AUTH_ROLE] = "Operator"
        else:
            upsert_user(uid, email, "User", None, display_name=display_name)
            st.session_state[AUTH_ROLE] = "User"
        st.session_state[AUTH_ORG_ID] = ""
        st.session_state[AUTH_DISPLAY_NAME] = display_name
        st.session_state[AUTH_ORG_NAME] = ""
        st.session_state.pop("oauth_url", None)
        return

    # 신규 사용자 — Google 등 OAuth(signup_profile 없음): 첫 계정은 운영자, 이후는 기본 기업 학생
    prior_count = count_all_users()
    if prior_count == 0:
        display_name = email.split("@")[0] if email else "사용자"
        upsert_user(uid, email, "Operator", None, display_name=display_name)
        st.session_state[AUTH_ROLE] = "Operator"
        st.session_state[AUTH_ORG_ID] = ""
        st.session_state[AUTH_DISPLAY_NAME] = display_name
        st.session_state[AUTH_ORG_NAME] = ""
    else:
        display_name = email.split("@")[0] if email else "사용자"
        org_id = _default_org_id()
        upsert_user(uid, email, "Student", org_id, display_name=display_name)
        st.session_state[AUTH_ROLE] = "Student"
        st.session_state[AUTH_ORG_ID] = org_id
        st.session_state[AUTH_DISPLAY_NAME] = display_name
        org = get_organization(org_id) if org_id else None
        st.session_state[AUTH_ORG_NAME] = str(org.get("org_name")) if org else ""
    st.session_state.pop("oauth_url", None)


def join_organization_with_invite_for_user_session() -> None:
    """Home — 역할이 User 인 계정이 초대 코드로 Teacher/Student 소속을 만든다."""
    import streamlit as st

    init_firebase()
    uid = str(st.session_state.get(AUTH_UID) or "").strip()
    if not uid:
        raise RuntimeError("로그인이 필요합니다.")
    prof = get_user(uid)
    if not prof:
        raise RuntimeError("프로필을 찾을 수 없습니다. 다시 로그인하세요.")
    if str(prof.get("role") or "") != "User":
        raise RuntimeError(
            "초대 소속은 **유저**로 가입한 계정에서만 사용할 수 있습니다."
        )
    code_raw = str(st.session_state.get("home_invite_code_input") or "").strip()
    code = code_raw.upper().replace(" ", "")
    if not code:
        raise RuntimeError("초대 코드를 입력하세요.")
    resolved = find_org_and_role_by_invite_code(code)
    if not resolved:
        raise RuntimeError("유효하지 않은 초대 코드입니다.")
    org_id, role = resolved
    if role not in ("Teacher", "Student"):
        raise RuntimeError("유효하지 않은 초대 역할입니다.")
    email = str(prof.get("email") or st.session_state.get(AUTH_EMAIL) or "")
    display_name = str(
        prof.get("display_name") or st.session_state.get(AUTH_DISPLAY_NAME) or ""
    ).strip() or (email.split("@")[0] if email else "사용자")
    org = get_organization(org_id)
    if not org:
        raise RuntimeError("기업(조직)을 찾을 수 없습니다.")
    if role == "Student":
        max_slots = int(org.get("max_slots") or 0)
        if count_students_in_org(org_id) >= max_slots:
            raise RuntimeError("학생 슬롯이 가득 찼습니다. 운영자에게 문의하세요.")
    upsert_user(uid, email, "User", None, display_name=display_name)
    submit_org_join_request(uid, email, display_name, org_id, role)
    st.session_state[AUTH_ROLE] = "User"
    st.session_state[AUTH_ORG_ID] = ""
    st.session_state[AUTH_DISPLAY_NAME] = display_name
    st.session_state[AUTH_ORG_NAME] = ""


def refresh_session_from_firestore() -> None:
    """Firestore Users 프로필을 세션에 반영(운영자 승인 후 역할 갱신 등)."""
    import streamlit as st

    init_firebase()
    uid = str(st.session_state.get(AUTH_UID) or "").strip()
    if not uid:
        return
    prof = get_user(uid)
    if not prof:
        return
    email = str(prof.get("email") or st.session_state.get(AUTH_EMAIL) or "")
    display_name = str(prof.get("display_name") or "").strip() or (
        email.split("@")[0] if email else ""
    )
    role = str(prof.get("role") or get_user_role(uid) or "User")
    org_id = _session_org_id_from_existing(prof)
    st.session_state[AUTH_EMAIL] = email
    st.session_state[AUTH_DISPLAY_NAME] = display_name
    st.session_state[AUTH_ROLE] = role
    st.session_state[AUTH_ORG_ID] = org_id
    org = get_organization(org_id) if org_id else None
    st.session_state[AUTH_ORG_NAME] = str(org.get("org_name") or "") if org else ""


def clear_auth_session() -> None:
    import streamlit as st

    for key in (
        AUTH_UID,
        AUTH_EMAIL,
        AUTH_DISPLAY_NAME,
        AUTH_ROLE,
        AUTH_ORG_ID,
        AUTH_ORG_NAME,
        AUTH_ID_TOKEN,
        AUTH_REFRESH_TOKEN,
        "oauth_state",
        "oauth_url",
        AUTH_VIEW,
        MGMT_SELECTED_ORG_ID,
        MGMT_VIEW_MODE,
        MGMT_DETAIL_TAB,
        TEACHER_SELECTED_CATEGORY_ID,
        TEACHER_SELECTED_SUB_ITEM_ID,
        TEACHER_VIEW_TAB,
        TEACHER_LESSON_FINGERPRINT,
    ):
        if key in st.session_state:
            del st.session_state[key]
