"""운영자 — 기업 세부 설정「교사·학생」탭."""

from __future__ import annotations

import streamlit as st

from services.auth_admin import create_email_password_user
from services.firestore_repo import (
    count_students_in_org,
    ensure_org_invite_codes,
    get_organization,
    list_users_by_org,
    regenerate_org_invite_code,
    upsert_user,
)


def _login_invite_url(code: str) -> str:
    """공유용 초대 링크. secrets 의 APP_BASE_URL 이 있으면 전체 URL, 없으면 경로만."""
    base = ""
    try:
        if hasattr(st, "secrets") and "APP_BASE_URL" in st.secrets:
            base = str(st.secrets["APP_BASE_URL"]).strip().rstrip("/")
    except Exception:
        pass
    path = f"/Login?invite={code}"
    return f"{base}{path}" if base else path


def render_org_people_tab(org_id: str, org_name: str) -> None:
    st.subheader("교사·학생")

    codes = ensure_org_invite_codes(org_id)
    detail = get_organization(org_id) or {}
    max_slots = int(detail.get("max_slots") or 0)
    student_n = count_students_in_org(org_id)

    st.markdown(f"**{org_name}** · 학생 슬롯 사용: **{student_n}** / **{max_slots}**")

    st.markdown("##### 초대 코드")
    st.caption(
        "아래 **짧은 링크**를 보내면 로그인 페이지가 열리고 초대 코드가 자동으로 채워집니다. "
        "(전체 URL을 쓰려면 secrets 에 `APP_BASE_URL` 을 설정하세요.)"
    )
    ct = codes.get("teacher", "")
    cs = codes.get("student", "")
    c1, c2 = st.columns(2)
    with c1:
        st.caption("교사용 코드")
        st.code(ct or "(생성 중)", language=None)
        if ct:
            st.caption("공유 링크 (교사)")
            st.code(_login_invite_url(ct), language=None)
        if st.button("교사 코드 재발급", key=f"reg_teacher_{org_id}"):
            regenerate_org_invite_code(org_id, "teacher")
            st.success("교사 초대 코드를 바꿨습니다. 이전 코드는 더 이상 쓸 수 없습니다.")
            st.rerun()
    with c2:
        st.caption("학생용 코드")
        st.code(cs or "(생성 중)", language=None)
        if cs:
            st.caption("공유 링크 (학생)")
            st.code(_login_invite_url(cs), language=None)
        if st.button("학생 코드 재발급", key=f"reg_student_{org_id}"):
            regenerate_org_invite_code(org_id, "student")
            st.success("학생 초대 코드를 바꿨습니다. 이전 코드는 더 이상 쓸 수 없습니다.")
            st.rerun()

    st.divider()
    st.markdown("##### 계정 직접 만들기")
    st.caption("이메일·임시 비밀번호로 계정을 만들면 해당 기업 소속 교사 또는 학생으로 등록됩니다.")
    with st.form(f"direct_create_{org_id}"):
        dc_email = st.text_input("이메일", key=f"dc_email_{org_id}")
        dc_pw = st.text_input("비밀번호", type="password", key=f"dc_pw_{org_id}")
        dc_name = st.text_input("닉네임(표시 이름)", key=f"dc_name_{org_id}")
        dc_role = st.selectbox("역할", ["Teacher", "Student"], key=f"dc_role_{org_id}")
        submitted = st.form_submit_button("계정 만들기", type="primary")

    if submitted:
        em = (st.session_state.get(f"dc_email_{org_id}") or "").strip()
        pw = st.session_state.get(f"dc_pw_{org_id}") or ""
        nick = (st.session_state.get(f"dc_name_{org_id}") or "").strip()
        role = st.session_state.get(f"dc_role_{org_id}") or "Student"
        if not em or not pw:
            st.error("이메일과 비밀번호를 입력하세요.")
        elif len(pw) < 6:
            st.error("비밀번호는 6자 이상이어야 합니다.")
        elif not nick:
            st.error("닉네임을 입력하세요.")
        else:
            org = get_organization(org_id)
            if not org:
                st.error("기업 정보를 찾을 수 없습니다.")
            elif role == "Student" and count_students_in_org(org_id) >= int(
                org.get("max_slots") or 0
            ):
                st.error("학생 슬롯이 가득 찼습니다.")
            else:
                try:
                    new_uid = create_email_password_user(
                        em, pw, display_name=nick
                    )
                    upsert_user(new_uid, em, role, org_id, display_name=nick)
                    st.success("계정을 만들었습니다. 해당 이메일로 로그인할 수 있습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    st.divider()
    st.markdown("##### 소속 사용자 목록")
    users = list_users_by_org(org_id)
    if not users:
        st.info("아직 등록된 교사·학생이 없습니다.")
    else:
        for u in users:
            em = str(u.get("email") or "")
            r = str(u.get("role") or "")
            dn = str(u.get("display_name") or "")
            st.markdown(f"- **{r}** · {dn or '(이름 없음)'} · `{em}`")
