"""Google Gemini API — 퀴즈·채팅 호출 스텁."""

import os


def get_api_key() -> str:
    """Streamlit Cloud에서는 st.secrets 사용 권장."""
    return os.environ.get("GEMINI_API_KEY", "")


def generate_quiz_from_text(_text: str) -> str:
    raise NotImplementedError("Gemini API 연동 후 구현")


def answer_with_context(_question: str, _context: str) -> str:
    raise NotImplementedError("Gemini API 연동 후 구현")
