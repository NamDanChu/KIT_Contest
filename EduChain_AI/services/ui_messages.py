"""에러·빈 상태·안내 문구 통일 (로컬 secrets / Streamlit Cloud 모두 안내)."""

from __future__ import annotations

import streamlit as st

# --- 문구 상수 (테스트·문서에서 재사용 가능) ---

GEMINI_KEY_HINT = (
    "**Gemini API 키**가 없습니다. 로컬은 `.streamlit/secrets.toml`, "
    "**Streamlit Cloud**는 앱 **Settings → Secrets**에 `GEMINI_API_KEY`를 넣어 주세요."
)

ORG_MISSING_HINT = (
    "소속 기업(`org_id`)이 설정되지 않았습니다. **운영자**에게 계정·기업 배정을 요청하세요."
)

TEACHER_NO_CATEGORY_HINT = (
    "배정된 수업(카테고리)이 없습니다. 운영자에게 **관리 → 콘텐츠**에서 과목 배정을 요청하세요."
)

STUDENT_NO_COURSE_HINT = (
    "배정된 수업이 없습니다. **개요**에서 안내를 확인하거나, 운영자에게 **관리 → 콘텐츠** 배정을 요청하세요."
)

STUDENT_PICK_COURSE_SIDEBAR = (
    "왼쪽 **수업 선택**에서 수업을 고른 뒤 **수업 개요** 또는 **수업 수강**을 누르세요."
)

TEACHER_SELECT_COURSE_HINT = (
    "왼쪽 **교사 메뉴**에서 **수업 선택**으로 수업을 먼저 고르세요."
)

VIDEO_NOT_SET_HINT = (
    "이 주차에 **영상 URL**이 없습니다. **수업 관리**에서 YouTube/Vimeo/HTML5 주소를 넣으면 재생됩니다."
)

VIDEO_URL_EMPTY_STUDENT = (
    "등록된 영상 URL이 없습니다. 담당 교사의 **수업 관리**에서 영상 링크를 등록하면 여기에 표시됩니다."
)

# 사이드바(짧은 한 줄)
SIDEBAR_ORG_MISSING = (
    "소속 기업 정보가 없습니다. 운영자에게 **배정**을 요청하세요."
)
STUDENT_SIDEBAR_NO_COURSE = "배정된 수업이 없습니다."


def warn_gemini_key_missing() -> None:
    st.warning(GEMINI_KEY_HINT)


def info_org_missing() -> None:
    st.warning(ORG_MISSING_HINT)


def info_teacher_no_category() -> None:
    st.info(TEACHER_NO_CATEGORY_HINT)


def info_student_no_course() -> None:
    st.info(STUDENT_NO_COURSE_HINT)


def info_student_pick_course_sidebar() -> None:
    st.info(STUDENT_PICK_COURSE_SIDEBAR)


def info_teacher_select_course() -> None:
    st.info(TEACHER_SELECT_COURSE_HINT)


def caption_video_not_set() -> None:
    st.caption(VIDEO_NOT_SET_HINT)


def info_video_url_empty_student() -> None:
    st.info(VIDEO_URL_EMPTY_STUDENT)


def sidebar_info_org_missing() -> None:
    st.sidebar.info(SIDEBAR_ORG_MISSING)


def sidebar_info_teacher_no_categories() -> None:
    st.sidebar.info(TEACHER_NO_CATEGORY_HINT)


def sidebar_info_student_no_categories() -> None:
    st.sidebar.info(STUDENT_SIDEBAR_NO_COURSE)
