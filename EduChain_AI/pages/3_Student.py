"""학생: 교안 기반 RAG Q&A."""

import streamlit as st

st.title("학생 · AI 튜터")

left, right = st.columns([1, 1])
with left:
    st.subheader("강의 자료")
    st.info("PDF/텍스트 미리보기 영역 (연동 예정)")
with right:
    st.subheader("AI 챗봇")
    st.chat_message("assistant").write("질문을 입력하면 교안을 인용해 답합니다.")

# TODO: services.rag_pipeline, ChatLogs 저장
