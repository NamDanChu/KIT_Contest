"""학생 — 첫 화면: 개요(정보·전체 교과목), 수업 선택 시: 수업 개요 / 수업 수강(현재 주차)."""

from __future__ import annotations

import streamlit as st

from services.firestore_repo import get_content_category, list_content_categories_for_student
from services.session_keys import (
    AUTH_DISPLAY_NAME,
    AUTH_EMAIL,
    AUTH_ORG_ID,
    AUTH_ORG_NAME,
    AUTH_ROLE,
    AUTH_UID,
    STUDENT_COURSE_SUB_TAB,
    STUDENT_LEARN_WEEK_ID,
    STUDENT_QUIZ_MIX_PHASE,
    STUDENT_QUIZ_WEEK_ID,
    STUDENT_SELECTED_CATEGORY_ID,
    STUDENT_VIEW_TAB,
)
from services.sidebar_helpers import (
    hide_login_nav_when_authed,
    render_login_gate_with_intro,
    render_sidebar_user_block,
    render_student_sidebar,
)
from services import ui_messages
from services.student_portal import (
    render_student_course_learn,
    render_student_course_overview,
    render_student_overview,
)
from services.student_quiz_mix import render_student_quiz_mix

st.set_page_config(
    page_title="학생 — EduChain AI",
    page_icon="🎓",
    layout="wide",
)

hide_login_nav_when_authed()

if not st.session_state.get(AUTH_UID):
    render_login_gate_with_intro(
        title="학생",
        description=(
            "왼쪽 **학생 메뉴**에서 **개요**와 배정된 **수업**을 선택할 수 있습니다.\n\n"
            "로그인 후 **Student** 역할 계정으로 이용하세요."
        ),
        login_button_key="login_gate_student",
    )

if st.session_state.get(AUTH_ROLE) != "Student":
    st.error("학생(Student) 계정만 이 메뉴를 사용할 수 있습니다.")
    st.stop()

uid = st.session_state[AUTH_UID]
org_id = (st.session_state.get(AUTH_ORG_ID) or "").strip()
display_name = str(st.session_state.get(AUTH_DISPLAY_NAME) or "")
email = str(st.session_state.get(AUTH_EMAIL) or "")
org_name = str(st.session_state.get(AUTH_ORG_NAME) or "")

if not org_id:
    ui_messages.info_org_missing()
    st.stop()

courses = list_content_categories_for_student(org_id, uid)
view = str(st.session_state.get(STUDENT_VIEW_TAB) or "overview")
if view not in ("overview", "course", "quiz_mix"):
    view = "overview"
    st.session_state[STUDENT_VIEW_TAB] = view
sub = str(st.session_state.get(STUDENT_COURSE_SUB_TAB) or "overview")
mix_phase = str(st.session_state.get(STUDENT_QUIZ_MIX_PHASE) or "setup")

# 사이드바(render_student_sidebar)와 동일하게 선택 수업을 맞춤. 안 맞추면
# STUDENT_LEARN_WEEK_ID만 남아 in_learn_player=True → 사이드바 숨김인데
# cat_id 없음 → "왼쪽 수업 선택" 안내만 나오는 상태가 됨.
_doc_ids = [str(c.get("_doc_id") or "") for c in courses if c.get("_doc_id")]
if not _doc_ids:
    st.session_state.pop(STUDENT_SELECTED_CATEGORY_ID, None)
else:
    _sel = st.session_state.get(STUDENT_SELECTED_CATEGORY_ID)
    if _sel is None or str(_sel) not in _doc_ids:
        st.session_state[STUDENT_SELECTED_CATEGORY_ID] = _doc_ids[0]

in_learn_player = (
    view == "course"
    and sub == "learn"
    and bool(st.session_state.get(STUDENT_LEARN_WEEK_ID))
)
in_quiz_exam = (
    view == "course"
    and sub == "learn"
    and bool(st.session_state.get(STUDENT_QUIZ_WEEK_ID))
)
in_quiz_mix_exam = view == "quiz_mix" and mix_phase in ("run", "done", "inf_run")

if not in_learn_player and not in_quiz_exam and not in_quiz_mix_exam:
    render_student_sidebar()
    render_sidebar_user_block(
        logout_key="sidebar_logout_student",
        management_org_name=st.session_state.get(AUTH_ORG_NAME) or None,
        show_top_divider=False,
    )

if view == "overview":
    render_student_overview(
        org_name=org_name,
        display_name=display_name,
        email=email,
        courses=courses,
    )
elif view == "quiz_mix":
    cat_id = st.session_state.get(STUDENT_SELECTED_CATEGORY_ID)
    if not courses:
        ui_messages.info_student_no_course()
        st.stop()
    if not cat_id:
        ui_messages.info_student_pick_course_sidebar()
        st.stop()

    cat = get_content_category(org_id, str(cat_id))
    if not cat:
        st.error("수업 정보를 불러올 수 없습니다.")
        st.stop()

    course_name = str(cat.get("name") or "(이름 없음)")
    render_student_quiz_mix(
        org_id=org_id,
        category_id=str(cat_id),
        course_name=course_name,
        student_uid=uid,
        student_email=email,
        display_name=display_name,
    )
else:
    cat_id = st.session_state.get(STUDENT_SELECTED_CATEGORY_ID)
    if not courses:
        ui_messages.info_student_no_course()
        st.stop()
    if not cat_id:
        ui_messages.info_student_pick_course_sidebar()
        st.stop()

    cat = get_content_category(org_id, str(cat_id))
    if not cat:
        st.error("수업 정보를 불러올 수 없습니다.")
        st.stop()

    if sub == "overview":
        render_student_course_overview(org_id=org_id, uid=uid, category=cat)
    else:
        render_student_course_learn(org_id=org_id, category_id=str(cat_id))
