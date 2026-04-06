"""공통: 로그인 / 회원가입 (Firebase Auth 연동 예정)."""

import streamlit as st

st.title("로그인")
st.caption("Firestore에서 role을 읽어 역할별 대시보드로 보내는 흐름을 여기에 구현합니다.")

# TODO: services.firebase_auth 연동 후 session_state에 auth_uid, auth_role, auth_org_id 설정
