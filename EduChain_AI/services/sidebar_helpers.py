"""Streamlit 사이드바 — 로그인 상태에 따른 네비 보조."""

from __future__ import annotations

import streamlit as st

from .session_keys import (
    AUTH_ORG_ID,
    AUTH_ROLE,
    AUTH_UID,
    MGMT_DETAIL_TAB,
    STUDENT_COURSE_SUB_TAB,
    STUDENT_LEARN_WEEK_ID,
    STUDENT_SELECTED_CATEGORY_ID,
    STUDENT_VIEW_TAB,
    TEACHER_SELECTED_CATEGORY_ID,
    TEACHER_SELECTED_SUB_ITEM_ID,
    TEACHER_VIEW_TAB,
)


# 멀티페이지 상단: `4_학생관리`는 Teacher 탭으로만 연결 → 목록에서 숨김
_HIDE_STUDENT_PAGE_NAV_CSS = """
<style>
    [data-testid="stSidebarNav"] a[href*="학생관리"],
    [data-testid="stSidebarNav"] a[href*="4_학생"],
    [data-testid="stSidebarNav"] li:has(a[href*="학생관리"]),
    [data-testid="stSidebarNav"] li:has(a[href*="4_학생"]) {
        display: none !important;
    }
</style>
"""

_HIDE_LOGIN_NAV_WHEN_AUTHED_CSS = """
<style>
    [data-testid="stSidebarNav"] li:has(> a[href*="Login"]),
    [data-testid="stSidebarNav"] li:has(> a[href*="1_Login"]),
    [data-testid="stSidebarNav"] a[href*="Login"],
    [data-testid="stSidebarNav"] a[href*="1_Login"] {
        display: none !important;
    }
</style>
"""


def _role_aware_multipage_nav_css() -> str:
    """로그인했을 때 역할에 맞지 않는 멀티페이지 링크 숨김. 역할 없음·미지정이면 Home만 노출."""
    if not st.session_state.get(AUTH_UID):
        return ""
    raw = st.session_state.get(AUTH_ROLE)
    role = str(raw).strip() if raw is not None else ""

    # href 부분 문자열(Streamlit 페이지 파일명·경로에 맞춤)
    if role == "Operator":
        hide_href_parts = ("3_Teacher", "Teacher", "5_Student", "Student")
    elif role == "Teacher":
        hide_href_parts = ("2_관리", "관리", "5_Student", "Student")
    elif role == "Student":
        hide_href_parts = ("2_관리", "관리", "3_Teacher", "Teacher")
    else:
        # Operator / Teacher / Student 가 아니면(미배정·빈 값·알 수 없음) 역할 전용 메뉴 전부 숨김
        hide_href_parts = (
            "2_관리",
            "관리",
            "3_Teacher",
            "Teacher",
            "5_Student",
            "Student",
        )

    rules = [
        f'[data-testid="stSidebarNav"] li:has(a[href*="{p}"]) {{ display: none !important; }}'
        for p in hide_href_parts
    ]
    return "<style>\n" + "\n".join(rules) + "\n</style>\n"


def hide_login_nav_when_authed() -> None:
    """사이드바 멀티페이지: 학생관리(리다이렉트 전용) 항목 항상 숨김. 로그인 시 Login 링크 숨김. 역할별로 불필요한 페이지 링크 숨김."""
    css = _HIDE_STUDENT_PAGE_NAV_CSS
    if st.session_state.get(AUTH_UID):
        css += _HIDE_LOGIN_NAV_WHEN_AUTHED_CSS
        css += _role_aware_multipage_nav_css()
    st.markdown(css, unsafe_allow_html=True)


def render_login_gate_with_intro(
    *,
    title: str,
    description: str,
    login_button_key: str = "login_gate_default",
) -> None:
    """비로그인 상태에서 사이드바로 이 페이지를 연 경우: 메뉴 설명 → 로그인 유도."""
    st.markdown(f"## {title}")
    st.markdown(description)
    st.warning("로그인이 필요합니다.")
    if st.button("로그인으로 이동", key=login_button_key):
        st.switch_page("pages/1_Login.py")
    st.stop()


_LABELS = {
    "basic": "기본 정보",
    "plan": "플랜·슬롯",
    "people": "교사·학생",
    "content": "콘텐츠·통계",
}
_ORDER = ["basic", "plan", "people", "content"]

# 세부 설정 카테고리 — 멀티페이지 네비(Home·관리 링크)와 비슷한 링크 톤 (로그아웃 제외)
_MGMT_NAV_STYLE = """
<style>
    section[data-testid="stSidebar"] button[data-testid="baseButton-secondary"]:not([aria-label="로그아웃"]) {
        width: 100%;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: inherit !important;
        font-weight: 400 !important;
        justify-content: flex-start !important;
        text-align: left !important;
        padding: 0.375rem 0.5rem !important;
        min-height: 2.5rem !important;
        border-radius: 0.375rem !important;
    }
    section[data-testid="stSidebar"] button[data-testid="baseButton-secondary"]:not([aria-label="로그아웃"]):hover {
        background-color: rgba(151, 166, 195, 0.15) !important;
    }
    section[data-testid="stSidebar"] button[data-testid="baseButton-primary"]:not([aria-label="로그아웃"]) {
        width: 100%;
        background: rgba(151, 166, 195, 0.2) !important;
        border: none !important;
        box-shadow: none !important;
        color: inherit !important;
        font-weight: 600 !important;
        justify-content: flex-start !important;
        text-align: left !important;
        padding: 0.375rem 0.5rem !important;
        min-height: 2.5rem !important;
        border-radius: 0.375rem !important;
    }
    section[data-testid="stSidebar"] button[data-testid="baseButton-primary"]:not([aria-label="로그아웃"]):hover {
        background-color: rgba(151, 166, 195, 0.28) !important;
    }
</style>
"""

# 교사 — 수업 카테고리 expander: 둥근 모서리·여백만 (구분선 최소화)
_TEACHER_CAT_STYLE = """
<style>
    section[data-testid="stSidebar"] [data-testid="stExpander"] {
        border-radius: 0.5rem !important;
        margin-bottom: 0.2rem !important;
    }
    .t-teacher-menu-block {
        margin-top: 0.5rem;
    }
</style>
"""

# 학생 수강 플레이어(student_portal._inject_learn_player_css)가 사이드바를 숨긴 뒤,
# 목록으로 돌아왔을 때 동일 세션에서 스타일이 남아 메뉴가 비어 보이는 문제 방지
_STUDENT_SIDEBAR_RESTORE_CSS = """
<style>
  section[data-testid="stSidebar"] {
    display: flex !important;
    flex-direction: column !important;
  }
  div[data-testid="collapsedControl"] {
    display: flex !important;
  }
</style>
"""


def render_mgmt_detail_category_sidebar() -> None:
    """세부 설정 모드: 페이지 네비(Home·관리) 아래 ~ 유저 블록 위까지.

    큰 제목 없이, 멀티페이지 네비와 비슷한 링크형으로 카테고리를 둡니다.
    """
    st.session_state.setdefault(MGMT_DETAIL_TAB, "basic")
    st.markdown(_MGMT_NAV_STYLE, unsafe_allow_html=True)

    current = st.session_state.get(MGMT_DETAIL_TAB, "basic")
    for key in _ORDER:
        label = _LABELS[key]
        if st.sidebar.button(
            label,
            key=f"mgmt_detail_cat_{key}",
            type="primary" if current == key else "secondary",
            use_container_width=True,
        ):
            if current != key:
                st.session_state[MGMT_DETAIL_TAB] = key
                st.rerun()


def get_teacher_category_sub_items(c: dict) -> list[dict[str, str]]:
    """운영자가 등록한 sub_items만 사용. 없으면 카테고리 단위 한 줄(제목과 중복되지 않게)."""
    from .firestore_repo import normalize_category_sub_items

    raw = normalize_category_sub_items(c.get("sub_items"))
    if raw:
        return raw
    return [{"id": "_category", "label": "이 수업 영역", "icon": "✓"}]


def render_teacher_sidebar() -> None:
    """교사: 학생 메뉴와 동일한 레이아웃 — 개요 / 수업 선택(selectbox) / 영역 선택(복수 시) / 탭 버튼."""
    from .firestore_repo import list_content_categories_for_teacher

    if st.session_state.get(AUTH_ROLE) != "Teacher":
        return

    uid = st.session_state.get(AUTH_UID)
    org_id = (st.session_state.get(AUTH_ORG_ID) or "").strip()

    st.markdown(_TEACHER_CAT_STYLE + _MGMT_NAV_STYLE, unsafe_allow_html=True)
    st.sidebar.markdown(
        '<div class="t-teacher-menu-block"></div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("**교사 메뉴**")

    if not uid or not org_id:
        st.sidebar.info("소속 기업 정보가 없습니다. 운영자에게 배정을 요청하세요.")
        return

    cats = list_content_categories_for_teacher(org_id, str(uid))
    doc_ids = [str(c.get("_doc_id") or "") for c in cats if c.get("_doc_id")]
    labels = {
        str(c.get("_doc_id") or ""): str(c.get("name") or "(이름 없음)")
        for c in cats
        if c.get("_doc_id")
    }

    st.session_state.setdefault(TEACHER_VIEW_TAB, "overview")
    view = str(st.session_state.get(TEACHER_VIEW_TAB) or "overview")
    if view not in ("overview", "students", "course_stats", "lesson_mgmt"):
        view = "overview"
        st.session_state[TEACHER_VIEW_TAB] = view

    if st.sidebar.button(
        "개요",
        key="t_nav_overview",
        type="primary" if view == "overview" else "secondary",
        use_container_width=True,
    ):
        st.session_state[TEACHER_VIEW_TAB] = "overview"
        st.switch_page("pages/3_Teacher.py")

    if not cats:
        st.sidebar.caption("수업 선택")
        st.sidebar.info(
            "배정된 수업 영역이 없습니다. 운영자에게 **관리 → 콘텐츠**에서 배정을 요청하세요."
        )
        st.session_state.pop(TEACHER_SELECTED_CATEGORY_ID, None)
        st.session_state.pop(TEACHER_SELECTED_SUB_ITEM_ID, None)
        return

    if (
        st.session_state.get(TEACHER_SELECTED_CATEGORY_ID) is None
        or str(st.session_state.get(TEACHER_SELECTED_CATEGORY_ID)) not in doc_ids
    ):
        st.session_state[TEACHER_SELECTED_CATEGORY_ID] = doc_ids[0]

    st.sidebar.selectbox(
        "수업 선택",
        options=doc_ids,
        format_func=lambda x: labels.get(x, x),
        key=TEACHER_SELECTED_CATEGORY_ID,
    )

    current_cid = str(st.session_state.get(TEACHER_SELECTED_CATEGORY_ID) or "")
    cur_cat = next(
        (x for x in cats if str(x.get("_doc_id") or "") == current_cid), None
    )
    if cur_cat:
        sub_list = get_teacher_category_sub_items(cur_cat)
        valid_sub = {str(x["id"]) for x in sub_list}
        sub_sel = st.session_state.get(TEACHER_SELECTED_SUB_ITEM_ID)
        if not sub_sel or str(sub_sel) not in valid_sub:
            st.session_state[TEACHER_SELECTED_SUB_ITEM_ID] = str(sub_list[0]["id"])

        if len(sub_list) > 1:
            sub_ids = [str(x["id"]) for x in sub_list]
            sub_labels = {
                str(x["id"]): f"{x.get('icon', '')} {x.get('label', '')}".strip()
                for x in sub_list
            }
            st.sidebar.selectbox(
                "영역 선택",
                options=sub_ids,
                format_func=lambda x: sub_labels.get(x, x),
                key=TEACHER_SELECTED_SUB_ITEM_ID,
            )

    if st.sidebar.button(
        "학생 관리",
        key="t_nav_students",
        type="primary" if view == "students" else "secondary",
        use_container_width=True,
    ):
        st.session_state[TEACHER_VIEW_TAB] = "students"
        st.switch_page("pages/3_Teacher.py")

    if st.sidebar.button(
        "수업 통계",
        key="t_nav_course_stats",
        type="primary" if view == "course_stats" else "secondary",
        use_container_width=True,
    ):
        st.session_state[TEACHER_VIEW_TAB] = "course_stats"
        st.switch_page("pages/3_Teacher.py")

    if st.sidebar.button(
        "수업 관리",
        key="t_nav_lesson",
        type="primary" if view == "lesson_mgmt" else "secondary",
        use_container_width=True,
    ):
        st.session_state[TEACHER_VIEW_TAB] = "lesson_mgmt"
        st.switch_page("pages/3_Teacher.py")

    if cur_cat:
        tdesc = str(cur_cat.get("description") or "").strip()
        if tdesc:
            st.sidebar.caption(tdesc[:120] + ("…" if len(tdesc) > 120 else ""))


# 하위 호환: 기존 import 이름 유지
render_teacher_sidebar_categories = render_teacher_sidebar


def render_student_sidebar() -> None:
    """학생: 교사 메뉴와 같은 톤 — 개요 / 수업 선택(selectbox) / 수업 개요·수업 수강."""
    from .firestore_repo import list_content_categories_for_student

    if st.session_state.get(AUTH_ROLE) != "Student":
        return

    uid = st.session_state.get(AUTH_UID)
    org_id = (st.session_state.get(AUTH_ORG_ID) or "").strip()

    st.markdown(
        _STUDENT_SIDEBAR_RESTORE_CSS + _TEACHER_CAT_STYLE + _MGMT_NAV_STYLE,
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        '<div class="t-teacher-menu-block"></div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("**학생 메뉴**")

    if not uid or not org_id:
        st.sidebar.info("소속 기업 정보가 없습니다. 운영자에게 문의하세요.")
        return

    cats = list_content_categories_for_student(org_id, str(uid))
    doc_ids = [str(c.get("_doc_id") or "") for c in cats if c.get("_doc_id")]
    labels = {
        str(c.get("_doc_id") or ""): str(c.get("name") or "(이름 없음)")
        for c in cats
        if c.get("_doc_id")
    }

    view = str(st.session_state.get(STUDENT_VIEW_TAB) or "overview")
    if view not in ("overview", "course"):
        view = "overview"
        st.session_state[STUDENT_VIEW_TAB] = view

    sub = str(st.session_state.get(STUDENT_COURSE_SUB_TAB) or "overview")
    if sub not in ("overview", "learn"):
        sub = "overview"
        st.session_state[STUDENT_COURSE_SUB_TAB] = sub

    if st.sidebar.button(
        "개요",
        key="st_nav_overview",
        type="primary" if view == "overview" else "secondary",
        use_container_width=True,
    ):
        st.session_state[STUDENT_VIEW_TAB] = "overview"
        st.session_state.pop(STUDENT_LEARN_WEEK_ID, None)
        st.switch_page("pages/5_Student.py")

    if not cats:
        st.sidebar.caption("수업 선택")
        st.sidebar.info("배정된 수업이 없습니다.")
        st.session_state.pop(STUDENT_SELECTED_CATEGORY_ID, None)
        return

    if (
        st.session_state.get(STUDENT_SELECTED_CATEGORY_ID) is None
        or str(st.session_state.get(STUDENT_SELECTED_CATEGORY_ID)) not in doc_ids
    ):
        st.session_state[STUDENT_SELECTED_CATEGORY_ID] = doc_ids[0]

    st.sidebar.selectbox(
        "수업 선택",
        options=doc_ids,
        format_func=lambda x: labels.get(x, x),
        key=STUDENT_SELECTED_CATEGORY_ID,
    )

    if st.sidebar.button(
        "수업 개요",
        key="st_nav_course_overview",
        type="primary" if view == "course" and sub == "overview" else "secondary",
        use_container_width=True,
    ):
        st.session_state[STUDENT_VIEW_TAB] = "course"
        st.session_state[STUDENT_COURSE_SUB_TAB] = "overview"
        st.session_state.pop(STUDENT_LEARN_WEEK_ID, None)
        st.switch_page("pages/5_Student.py")

    if st.sidebar.button(
        "수업 수강",
        key="st_nav_course_learn",
        type="primary" if view == "course" and sub == "learn" else "secondary",
        use_container_width=True,
    ):
        st.session_state[STUDENT_VIEW_TAB] = "course"
        st.session_state[STUDENT_COURSE_SUB_TAB] = "learn"
        # 플레이어에 들어가 있던 주차 ID가 남으면 주차 목록 대신 바로 강의로 진입함 → 항상 목록부터
        st.session_state.pop(STUDENT_LEARN_WEEK_ID, None)
        st.switch_page("pages/5_Student.py")

    cur = next(
        (x for x in cats if str(x.get("_doc_id") or "") == str(st.session_state.get(STUDENT_SELECTED_CATEGORY_ID))),
        None,
    )
    if cur:
        tdesc = str(cur.get("description") or "").strip()
        if tdesc:
            st.sidebar.caption(tdesc[:120] + ("…" if len(tdesc) > 120 else ""))


def render_sidebar_user_block(
    *,
    logout_key: str = "sidebar_logout",
    management_org_name: str | None = None,
    show_top_divider: bool = True,
) -> None:
    """로그인 시 사이드바 하단에 이름·이메일·역할·(선택)기업명·로그아웃."""
    from .auth_session import clear_auth_session
    from .session_keys import AUTH_DISPLAY_NAME, AUTH_EMAIL, AUTH_ROLE

    if not st.session_state.get(AUTH_UID):
        return
    if show_top_divider:
        st.sidebar.divider()
    else:
        st.sidebar.markdown(
            '<div style="height:0.75rem"></div>',
            unsafe_allow_html=True,
        )
    st.sidebar.caption(
        f"{st.session_state.get(AUTH_DISPLAY_NAME, '')} · {st.session_state.get(AUTH_EMAIL, '')}"
    )
    st.sidebar.caption(f"역할: {st.session_state.get(AUTH_ROLE, '')}")
    if management_org_name:
        st.sidebar.caption(f"기업: {management_org_name}")
    if st.sidebar.button("로그아웃", key=logout_key):
        clear_auth_session()
        st.rerun()
