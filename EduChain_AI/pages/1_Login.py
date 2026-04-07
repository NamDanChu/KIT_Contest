"""로그인 / 회원가입 화면 전환 + Google 로그인."""

from __future__ import annotations

import streamlit as st

from services.auth_session import apply_firebase_rest_result, clear_auth_session
from services.sidebar_helpers import hide_login_nav_when_authed
from services.firebase_auth_rest import (
    sign_in_email,
    sign_in_with_google_id_token,
    sign_up_email,
)
from services.google_oauth_flow import create_authorization_url, exchange_code_for_id_token
from services.firestore_repo import find_org_and_role_by_invite_code
from services.session_keys import AUTH_EMAIL, AUTH_UID, AUTH_VIEW

hide_login_nav_when_authed()

# --- Google OAuth 콜백 (?code= &state=) ---
params = st.query_params
if "code" in params and "state" in params:
    saved = st.session_state.get("oauth_state")
    if saved and params.get("state") == saved:
        try:
            id_tok = exchange_code_for_id_token(str(params["code"]))
            data = sign_in_with_google_id_token(id_tok)
            apply_firebase_rest_result(data)
            st.session_state.pop("oauth_state", None)
            for k in list(params.keys()):
                try:
                    del st.query_params[k]
                except Exception:
                    pass
            st.success("Google 로그인되었습니다.")
            st.rerun()
        except Exception as e:
            st.error(str(e))
    else:
        st.warning("OAuth state 가 일치하지 않습니다. 다시 시도하세요.")
        clear_auth_session()
        for k in list(params.keys()):
            try:
                del st.query_params[k]
            except Exception:
                pass

# --- 초대 짧은 링크 (?invite=코드) — 초대 가입 화면 + 코드 자동 입력 ---
if not st.session_state.get(AUTH_UID):
    inv_qp = st.query_params.get("invite")
    if inv_qp is not None and str(inv_qp).strip():
        code_q = str(inv_qp).strip().upper().replace(" ", "")
        if code_q:
            st.session_state[AUTH_VIEW] = "invite_signup"
            st.session_state["invite_code_input"] = code_q
            try:
                del st.query_params["invite"]
            except Exception:
                pass
            st.rerun()

# --- 이미 로그인 ---
if st.session_state.get(AUTH_UID):
    st.success(f"로그인됨: {st.session_state.get(AUTH_EMAIL, '')}")
    if st.button("로그아웃"):
        clear_auth_session()
        st.rerun()
    st.stop()

st.session_state.setdefault(AUTH_VIEW, "login")
view = st.session_state[AUTH_VIEW]

# --- 로그인 / 회원가입 본문 ---
if view == "login":
    st.title("로그인")

    with st.form("form_login", clear_on_submit=False):
        st.text_input("이메일", key="login_email", autocomplete="email")
        st.text_input("비밀번호", type="password", key="login_password")
        submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)

    email_val = (st.session_state.get("login_email") or "").strip()
    pw_val = st.session_state.get("login_password") or ""

    if submitted:
        if not email_val or not pw_val:
            st.error("이메일과 비밀번호를 모두 입력하세요.")
        else:
            try:
                data = sign_in_email(email_val, pw_val)
                apply_firebase_rest_result(data)
                st.success("로그인했습니다.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    c1, c2 = st.columns(2)
    with c1:
        if st.button("회원가입", use_container_width=True):
            st.session_state[AUTH_VIEW] = "signup"
            st.session_state.pop("oauth_url", None)
            st.rerun()
    with c2:
        if st.button("초대 코드로 가입", use_container_width=True):
            st.session_state[AUTH_VIEW] = "invite_signup"
            st.session_state.pop("oauth_url", None)
            st.rerun()

elif view == "signup":
    st.title("회원가입")
    st.caption(
        "서비스에 **첫 번째로** 가입하면 **운영자(Operator)** 로 등록되며, "
        "입력한 기업이 첫 조직으로 생성됩니다. 이후 가입자는 일반 **학생** 역할로 시작합니다."
    )

    with st.form("form_signup", clear_on_submit=False):
        st.text_input("이름", key="signup_display_name", autocomplete="name")
        st.text_input("학원 또는 학교(기업) 이름", key="signup_org_name")
        st.text_input("이메일", key="signup_email", autocomplete="email")
        st.text_input("비밀번호", type="password", key="signup_password")
        submitted = st.form_submit_button("회원가입", type="primary", use_container_width=True)

    email_val = (st.session_state.get("signup_email") or "").strip()
    pw_val = st.session_state.get("signup_password") or ""
    name_val = (st.session_state.get("signup_display_name") or "").strip()
    org_val = (st.session_state.get("signup_org_name") or "").strip()

    if submitted:
        if not email_val or not pw_val:
            st.error("이메일과 비밀번호를 모두 입력하세요.")
        elif not name_val or not org_val:
            st.error("이름과 학원·학교(기업) 이름을 모두 입력하세요.")
        else:
            try:
                data = sign_up_email(email_val, pw_val)
                apply_firebase_rest_result(
                    data,
                    signup_profile={
                        "display_name": name_val,
                        "org_name": org_val,
                    },
                )
                st.success("회원가입이 완료되었습니다.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    if st.button("로그인으로", use_container_width=True):
        st.session_state[AUTH_VIEW] = "login"
        st.session_state.pop("oauth_url", None)
        st.rerun()

elif view == "invite_signup":
    st.title("초대 코드로 가입")
    st.caption(
        "운영자에게 받은 **교사용** 또는 **학생용** 초대 코드를 입력한 뒤, "
        "닉네임·이메일·비밀번호를 설정합니다. 닉네임은 기업에서 구분용으로 표시됩니다. "
        "**`…/Login?invite=코드`** 링크로 들어오면 코드가 자동으로 채워집니다."
    )
    with st.form("form_invite_signup", clear_on_submit=False):
        st.text_input("초대 코드", key="invite_code_input", placeholder="예: ABC12XY3")
        st.text_input("닉네임(표시 이름)", key="invite_nickname", autocomplete="nickname")
        st.text_input("이메일", key="invite_email", autocomplete="email")
        st.text_input("비밀번호", type="password", key="invite_password")
        inv_sub = st.form_submit_button("가입 완료", type="primary", use_container_width=True)

    code_raw = (st.session_state.get("invite_code_input") or "").strip()
    nick = (st.session_state.get("invite_nickname") or "").strip()
    em = (st.session_state.get("invite_email") or "").strip()
    pw = st.session_state.get("invite_password") or ""

    if inv_sub:
        if not code_raw or not nick or not em or not pw:
            st.error("초대 코드, 닉네임, 이메일, 비밀번호를 모두 입력하세요.")
        elif len(pw) < 6:
            st.error("비밀번호는 6자 이상이어야 합니다.")
        else:
            resolved = find_org_and_role_by_invite_code(code_raw)
            if not resolved:
                st.error("유효하지 않은 초대 코드입니다. 코드를 확인하세요.")
            else:
                org_id, role = resolved
                try:
                    data = sign_up_email(em, pw)
                    apply_firebase_rest_result(
                        data,
                        signup_profile={
                            "invite_org_id": org_id,
                            "invite_role": role,
                            "display_name": nick,
                        },
                    )
                    st.success("가입이 완료되었습니다. 로그인되었습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    if st.button("로그인 화면으로", use_container_width=True):
        st.session_state[AUTH_VIEW] = "login"
        st.session_state.pop("oauth_url", None)
        st.rerun()

# --- Google (로그인·일반 회원가입만; 초대 가입 화면에서는 숨김) ---
if view in ("login", "signup"):
    st.divider()
    if st.button("Google로 로그인", use_container_width=True):
        try:
            url, state = create_authorization_url()
            st.session_state["oauth_state"] = state
            st.session_state["oauth_url"] = url
            st.rerun()
        except Exception as e:
            st.error(str(e))

    oauth_url = st.session_state.get("oauth_url")
    if oauth_url:
        st.link_button("Google 계정으로 이동", url=oauth_url, use_container_width=True)
