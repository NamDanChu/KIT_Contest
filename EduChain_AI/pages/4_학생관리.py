"""호환: 멀티페이지 링크는 교사 화면의 «학생 관리» 탭으로 연결됩니다."""

from __future__ import annotations

import streamlit as st

from services.sidebar_helpers import hide_login_nav_when_authed, render_login_gate_with_intro
from services.session_keys import AUTH_ROLE, AUTH_UID, TEACHER_VIEW_TAB

hide_login_nav_when_authed()

if not st.session_state.get(AUTH_UID):
    render_login_gate_with_intro(
        title="학생 관리",
        description=(
            "학생 목록은 **교사** 화면에서 수업을 고른 뒤, 본문 **학생 관리** 탭에서 "
            "확인합니다. 로그인 후 교사 계정으로 이용하세요."
        ),
        login_button_key="login_gate_student_mgmt_compat",
    )

if st.session_state.get(AUTH_ROLE) != "Teacher":
    st.error("교사(Teacher) 계정만 이 메뉴를 사용할 수 있습니다.")
    st.stop()

st.session_state[TEACHER_VIEW_TAB] = "students"
st.switch_page("pages/3_Teacher.py")
