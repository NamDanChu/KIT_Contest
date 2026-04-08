"""EduChain AI — Streamlit 진입점."""

import streamlit as st

from services.auth_session import (
    join_organization_with_invite_for_user_session,
    refresh_session_from_firestore,
)
from services.firestore_repo import get_organization, get_user
from services.sidebar_helpers import (
    hide_login_nav_when_authed,
    render_sidebar_user_block,
)
from services.session_keys import (
    AUTH_ROLE,
    AUTH_UID,
    AUTH_ORG_NAME,
    MGMT_DETAIL_TAB,
    MGMT_SELECTED_ORG_ID,
    MGMT_VIEW_MODE,
)

st.set_page_config(
    page_title="EduChain AI",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

hide_login_nav_when_authed()

# Home 진입 시 관리 화면의「기업 세부 설정」세션만 초기화 (본문 뒤로가기 제거 시 목록 복귀 경로)
st.session_state.pop(MGMT_VIEW_MODE, None)
st.session_state.pop(MGMT_SELECTED_ORG_ID, None)
st.session_state.pop(MGMT_DETAIL_TAB, None)

if st.session_state.get(AUTH_UID):
    refresh_session_from_firestore()
    _role_home = st.session_state.get(AUTH_ROLE)
    # 교사·학생 전용 사이드바(개요/수업 선택 등)는 각각 Teacher·Student 페이지에서만 표시.
    # Home은 멀티페이지 상단 네비(Home·관리·Teacher·Student) + 아래 사용자 블록만 둡니다.
    _mgmt_org = (
        st.session_state.get(AUTH_ORG_NAME) or None
        if _role_home in ("Teacher", "Student")
        else None
    )
    render_sidebar_user_block(
        logout_key="sidebar_logout_home",
        management_org_name=_mgmt_org,
        show_top_divider=True,
    )
else:
    if st.sidebar.button("로그인 · 회원가입"):
        st.switch_page("pages/1_Login.py")

st.title("EduChain AI")
st.caption("AI 에이전트와 실시간 클라우드가 결합된 초개인화 학습 생태계")

_role = st.session_state.get(AUTH_ROLE)
_uid = st.session_state.get(AUTH_UID)
if _role == "Teacher":
    st.info(
        "왼쪽 **교사 메뉴**에서 📁 수업을 고른 뒤, 같은 메뉴의 **개요·학생 관리·수업 통계·수업 관리**로 화면을 바꿉니다. "
        "**Teacher** 페이지에서 본문이 바뀝니다. 배정은 운영자가 **관리 → 콘텐츠**에서 합니다."
    )
elif _role == "Operator":
    st.info(
        "로그인 후 **관리** 메뉴에서 학원·학교(기업)를 등록하고 선택해 세부 기능을 사용합니다. "
        "로그인·회원가입은 **1_Login** 페이지입니다."
    )
elif _role == "Student":
    st.info(
        "왼쪽 상단 **Student**(멀티페이지)를 눌러 **학생** 화면으로 이동한 뒤, "
        "**학생 메뉴**에서 **개요**·**수업 선택**·**수업 수강**을 이용하세요."
    )
elif _role == "User":
    _prof_u = get_user(str(_uid)) if _uid else None
    _pending = bool(_prof_u and _prof_u.get("membership_pending"))
    if _pending:
        _oid = str(_prof_u.get("pending_org_id") or "").strip()
        _pr = str(_prof_u.get("pending_role") or "")
        _oname = ""
        if _oid:
            _ogr = get_organization(_oid)
            _oname = str(_ogr.get("org_name") or "") if _ogr else ""
        st.warning(
            f"**소속 승인 대기 중**입니다. "
            f"({_oname or '기업'} · 신청: **{_pr or '—'}**)\n\n"
            "운영자가 **관리 → 교사·학생 → 가입 승인 대기**에서 승인하면 "
            "**Teacher** / **Student** 메뉴를 사용할 수 있습니다."
        )
        st.caption("승인 후 자동으로 반영됩니다. 메뉴가 안 바뀌면 페이지를 새로고침하세요.")
    else:
        st.info(
            "아직 기업(학원)에 소속되지 않았습니다. 운영자에게 받은 **초대 코드**를 입력하면 "
            "소속을 **신청**할 수 있습니다. (운영자 승인 후 교사/학생으로 전환됩니다.)"
        )
        st.caption(
            "초대 코드는 **관리 → 교사·학생**에서 발급됩니다. "
            "`…/Login?invite=코드` 링크로 가입할 때도 같은 절차입니다."
        )
        with st.form("home_invite_join"):
            st.text_input(
                "초대 코드",
                key="home_invite_code_input",
                placeholder="예: ABC12XY3",
            )
            submitted_inv = st.form_submit_button(
                "소속 신청", type="primary", use_container_width=True
            )
        if submitted_inv:
            try:
                join_organization_with_invite_for_user_session()
                st.success(
                    "신청이 접수되었습니다. 운영자 승인 후 **Teacher** 또는 **Student** 메뉴가 열립니다."
                )
                st.rerun()
            except Exception as e:
                st.error(str(e))
elif _uid:
    st.warning(
        "이 계정에는 아직 **역할(Operator / Teacher / Student)이 배정되지 않았습니다.** "
        "운영자에게 문의하거나, 초대 가입·프로필 동기화를 확인하세요. "
        "역할이 없을 때는 상단 메뉴에서 **Home**만 이용할 수 있습니다."
    )
else:
    st.info(
        "로그인 후 **관리** 메뉴에서 학원·학교(기업)를 등록하고 선택해 세부 기능을 사용합니다. "
        "로그인·회원가입은 **1_Login** 페이지입니다."
    )
