"""EduChain AI — Streamlit 진입점."""

import streamlit as st

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
