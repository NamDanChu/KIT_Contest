"""EduChain AI — Streamlit 진입점."""

import streamlit as st

st.set_page_config(
    page_title="EduChain AI",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("EduChain AI")
st.caption("AI 에이전트와 실시간 클라우드가 결합된 초개인화 학습 생태계")

st.info(
    "왼쪽 사이드바에서 페이지를 선택하세요. "
    "로그인·Firebase·RAG 연동은 `services/` 모듈을 채운 뒤 각 `pages/`에서 호출합니다."
)
