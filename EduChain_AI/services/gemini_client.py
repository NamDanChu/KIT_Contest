"""Google Gemini API — 수업 관리 요약·키워드·퀴즈·노트."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import google.generativeai as genai

try:
    from google.api_core import exceptions as google_exceptions
except ImportError:
    google_exceptions = None  # type: ignore[misc, assignment]


def get_api_key() -> str:
    """Streamlit secrets → 환경 변수."""
    return _secrets_get("GEMINI_API_KEY")


def _secrets_get(key: str) -> str:
    try:
        import streamlit as st

        if hasattr(st, "secrets") and key in st.secrets:
            v = st.secrets[key]
            if v and str(v).strip():
                return str(v).strip()
    except Exception:
        pass
    return (os.environ.get(key) or "").strip()


def get_model_name() -> str:
    v = _secrets_get("GEMINI_MODEL")
    if v:
        return v
    # 2.0-flash 는 일부 키에서 free tier limit:0 보고 → 기본은 lite 쪽 우선
    return "gemini-2.5-flash-lite"


def _extra_model_fallbacks() -> list[str]:
    """쉼표 구분 — secrets 또는 환경 변수 GEMINI_MODEL_FALLBACKS."""
    raw = _secrets_get("GEMINI_MODEL_FALLBACKS")
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _default_model_fallback_chain() -> list[str]:
    return [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
    ]


def models_to_try_in_order() -> list[str]:
    """첫 요청 모델 + 중복 제거한 대체 모델 목록."""
    seen: set[str] = set()
    out: list[str] = []
    for m in [get_model_name(), *_extra_model_fallbacks(), *_default_model_fallback_chain()]:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _text_from_response(resp: Any) -> str:
    try:
        t = (resp.text or "").strip()
        if t:
            return t
    except Exception:
        pass
    try:
        c = resp.candidates[0]
        parts_out: list[str] = []
        for part in c.content.parts:
            if hasattr(part, "text") and part.text:
                parts_out.append(part.text)
        return "\n".join(parts_out).strip()
    except Exception:
        return ""


def _parse_retry_seconds(err: BaseException) -> float | None:
    m = re.search(r"retry in ([0-9.]+)\s*s", str(err), re.I)
    if m:
        return min(float(m.group(1)) + 1.0, 120.0)
    return None


def _is_quota_or_rate_limit(err: BaseException) -> bool:
    if google_exceptions and isinstance(err, google_exceptions.ResourceExhausted):
        return True
    s = str(err).lower()
    return "429" in s or "quota" in s or "resource exhausted" in s


def _should_switch_model_and_retry(err: BaseException) -> bool:
    """이 오르면 같은 키로 재시도해도 소용없어 **다른 모델**로 넘긴다."""
    s = str(err).lower()
    if "limit: 0" in s or "limit:0" in s:
        return True
    if "404" in s and ("not found" in s or "is not found" in s):
        return True
    if "not supported for generatecontent" in s:
        return True
    return False


def format_quota_error_message(
    err: BaseException,
    *,
    tried_models: list[str] | None = None,
) -> str:
    """429·할당량 소진 시 사용자 안내 (UI에 그대로 표시)."""
    s = str(err)
    low = s.lower()
    parts = [
        "Gemini API **할당량(429)** 으로 요청이 거절되었습니다.",
        "",
        "1. **잠시 뒤** 같은 작업을 다시 시도 (분당 제한인 경우)",
        "2. [API 한도 안내](https://ai.google.dev/gemini-api/docs/rate-limits) · "
        "[AI Studio](https://aistudio.google.com/) 에서 키·사용량 확인",
    ]
    if tried_models:
        parts.append(f"3. 앱이 **순서대로 시도한 모델:** `{', '.join(tried_models)}`")
    if "limit: 0" in low or "limit:0" in low:
        parts.append(
            "4. **`limit: 0`** 이면 해당 키로 그 모델 **무료 호출이 막힌 상태**일 수 있습니다. "
            "Google Cloud **결제** 연동을 검토하거나, `secrets.toml` 의 `GEMINI_MODEL` / "
            "`GEMINI_MODEL_FALLBACKS` 로 다른 모델을 지정하세요."
        )
    parts.extend(["", f"**원본:** `{s[:900]}{'…' if len(s) > 900 else ''}`"])
    return "\n".join(parts)


def _generate(prompt: str) -> str:
    key = get_api_key()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY 가 없습니다. .streamlit/secrets.toml 에 GEMINI_API_KEY 를 넣거나 "
            "환경 변수로 설정하세요."
        )
    genai.configure(api_key=key)
    order = models_to_try_in_order()
    last: BaseException | None = None
    max_attempts = 6

    for model_name in order:
        model = genai.GenerativeModel(model_name)
        for attempt in range(max_attempts):
            try:
                resp = model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.4,
                        "max_output_tokens": 8192,
                    },
                )
                out = _text_from_response(resp)
                if not out:
                    raise RuntimeError(
                        "Gemini 응답이 비었거나 차단되었습니다. 프롬프트를 줄이거나 재시도하세요."
                    )
                return out
            except Exception as e:
                last = e
                if _should_switch_model_and_retry(e):
                    break
                if not _is_quota_or_rate_limit(e):
                    raise
                if attempt >= max_attempts - 1:
                    break
                delay = _parse_retry_seconds(e) or min(90.0, 3.0 * (2**attempt))
                time.sleep(delay)

    if last is not None:
        raise RuntimeError(
            format_quota_error_message(last, tried_models=order),
        ) from last
    raise RuntimeError("Gemini 호출에 실패했습니다.")


def summarize_lesson_context(
    *,
    title: str,
    learning_goals: str,
    source_text: str,
    meta_hint: str,
) -> str:
    """이번 주차 핵심 요약 (RAG 미리보기용)."""
    prompt = f"""당신은 교육용 AI 어시스턴트입니다. 아래는 한 수업 주차의 학습 목표와 교안/자막 일부입니다.

[주차 제목] {title}
[학습 목표·키워드]
{learning_goals or "(없음)"}

[맥락 메타데이터 — RAG 격리용]
{meta_hint}

[교안·자막 본문]
{source_text[:12000]}

요구사항:
1. 이번 주차 핵심 개념을 5~8문장으로 요약하라.
2. 학생이 꼭 알아야 할 용어를 bullet로 나열하라.
3. 마크다운으로 작성하라.
"""
    return _generate(prompt)


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _parse_summary_keywords_payload(raw: str) -> tuple[str, str]:
    """한 번에 받은 JSON/텍스트에서 요약·키워드 줄을 분리."""
    t = _strip_json_fence(raw)
    try:
        obj = json.loads(t)
        sm = str(obj.get("summary_markdown") or "").strip()
        kw = str(obj.get("keywords_csv") or "").strip()
        if sm:
            return sm, kw
    except json.JSONDecodeError:
        pass
    return raw.strip(), ""


def summarize_lesson_with_keywords_one_shot(
    *,
    title: str,
    learning_goals: str,
    source_text: str,
    meta_hint: str,
    max_terms: int = 12,
) -> tuple[str, str]:
    """
    요약 + 키워드를 **한 번의 generate_content** 로 받는다 (무료 티어 호출 수 절반).
    반환: (ai_summary_markdown, keywords_comma_separated)
    """
    prompt = f"""교육용 AI이다. 아래 수업 자료를 읽고 요약과 키워드를 만든다.

[주차 제목] {title}
[학습 목표]
{learning_goals or "(없음)"}

[맥락 메타데이터]
{meta_hint}

[교안·자막 본문]
{source_text[:12000]}

출력 형식 (매우 중요):
- **JSON 한 개만** 출력한다. 앞뒤에 설명·인사·마크다운 코드펜스를 넣지 마라.
- summary_markdown: 이번 주차 핵심을 5~8문장으로, 학생이 알아야 할 용어는 bullet로. 마크다운 문자열.
- keywords_csv: 시험·질문에 쓸 한국어 핵심 용어만 쉼표로 구분, {max_terms}개 이하.

예시 형태:
{{"summary_markdown": "# ...", "keywords_csv": "용어1, 용어2"}}
"""
    raw = _generate(prompt)
    summary, kw = _parse_summary_keywords_payload(raw)
    if not summary:
        raise RuntimeError("Gemini가 요약 JSON을 반환하지 않았습니다. 다시 시도하세요.")
    # 키워드가 비면 추가 API 호출은 하지 않음(할당량 절약). 우측 «키워드 재실행» 사용.
    return summary, kw


def extract_keywords_line(
    *,
    learning_goals: str,
    source_text: str,
    max_terms: int = 12,
) -> str:
    """쉼표로 구분된 키워드 한 줄."""
    prompt = f"""학습 목표와 교안에서 시험·질문에 쓰기 좋은 핵심 용어만 뽑아라.

[학습 목표]
{learning_goals or "(없음)"}

[교안·자막 일부]
{source_text[:8000]}

출력: 한국어 핵심 용어만 쉼표로 {max_terms}개 이내, 다른 설명 없이."""
    return _generate(prompt)


def generate_quiz_markdown(
    *,
    title: str,
    learning_goals: str,
    source_text: str,
    num_questions: int = 5,
    difficulty: str = "중",
) -> str:
    """객관식 퀴즈 마크다운."""
    prompt = f"""다음 자료를 바탕으로 객관식 {num_questions}문항을 만든다. 난이도: {difficulty}.

[주차] {title}
[학습 목표]
{learning_goals or "(없음)"}

[근거 자료]
{source_text[:12000]}

규칙:
- 각 문항에 4지선다, 정답 번호, 짧은 해설을 포함한다.
- 마크다운으로 번호 목록 형식으로 출력한다.
"""
    return _generate(prompt)


def generate_quiz_items_json(
    *,
    title: str,
    learning_goals: str,
    source_text: str,
    num_questions: int = 5,
    difficulty: str = "중",
) -> list[dict[str, Any]]:
    """
    학생 화면 채점용 4지선다 문항 배열.
    각 원소: text, options(4), correct(0~3), explanation(해설, 한두 문장)
    """
    n = max(1, min(50, int(num_questions)))
    prompt = f"""교육용 객관식 {n}문항을 만든다. 난이도: {difficulty}.

[주차 제목] {title}
[학습 목표]
{learning_goals or "(없음)"}

[근거 자료]
{source_text[:12000]}

출력 규칙 (매우 중요):
- **JSON 배열만** 출력한다. 앞뒤 설명·인사·마크다운 코드펜스를 넣지 마라.
- 배열 길이는 정확히 {n}개.
- 각 원소는 객체:
  - "text": 문항 본문
  - "options": 보기 문자열 정확히 4개
  - "correct": 정답 인덱스 0~3
  - "explanation": 왜 그 보기가 정답인지 **1~3문장** 한국어 해설 (필수)
- 보기는 항상 4개. 한국어로 작성한다.

예시 (형식만 참고):
[{{"text":"...","options":["가","나","다","라"],"correct":0,"explanation":"근거 문장에 따르면 ..."}}]
"""
    raw = _generate(prompt)
    t = _strip_json_fence(raw)
    try:
        data = json.loads(t)
    except json.JSONDecodeError as e:
        raise RuntimeError("Gemini가 올바른 JSON 배열을 반환하지 않았습니다. 다시 시도하세요.") from e
    if not isinstance(data, list):
        raise RuntimeError("퀴즈 JSON은 배열이어야 합니다.")
    from services.quiz_items import normalize_quiz_items

    return normalize_quiz_items(data)


def generate_one_page_note(
    *,
    title: str,
    learning_goals: str,
    source_text: str,
) -> str:
    """학생 배포용 한 페이지 요약 노트."""
    prompt = f"""학생에게 나눠줄 **한 페이지 분량**의 복습 노트를 작성하라. 친절한 말투.

[주차] {title}
[학습 목표]
{learning_goals or "(없음)"}

[근거 자료]
{source_text[:12000]}

구성: 핵심 정리 → 용어 정리 → 예시 1개 → 복습 체크 질문 3개. 마크다운."""
    return _generate(prompt)


def answer_with_context(question: str, context: str) -> str:
    """일반 RAG 답변 (추후 챗봇 연동)."""
    prompt = f"""다음 [참고 자료]만 근거로 [질문]에 답하라. 모르면 모른다고 하라.

[참고 자료]
{context[:16000]}

[질문]
{question}
"""
    return _generate(prompt)


def analyze_course_statistics(
    *,
    course_name: str,
    n_students: int,
    weeks_summary_block: str,
    quiz_block: str,
    questions_digest: str,
) -> str:
    """
    교사 수업 통계 화면 — 수강 인원·주차별 완료·질문 요약을 바탕으로 수업 전반을 분석한다.
    퀴즈 상세는 아직 없을 수 있음.
    """
    prompt = f"""당신은 교육 운영을 돕는 데이터 분석가입니다. 아래는 **한 수업(코스)** 에 대한 집계입니다.
퀴즈·시험의 문항별 정오답 데이터가 비어 있거나 '추후'로 표시되어 있으면 **가정하지 말고**, 있는 수치만 사용하라.

[수업명] {course_name}
[이 수업 수강(배정) 학생 수] {n_students}명

[주차별 요약 — 완료 인원, 주차 제목·요약 등]
{weeks_summary_block[:12000]}

[퀴즈·평가 관련 집계 — 없으면 (없음)]
{quiz_block[:4000]}

[학생 AI 질문 요약 — 주차·질문 일부]
{questions_digest[:14000]}

요구사항 (한국어, 마크다운):
1. **한 줄 요약** — 이 수업의 전반적 참여·진행 상태
2. **주차별 인사이트** — 완료율·질문 패턴에서 드러나는 점 (불릿)
3. **잘 되고 있는 점** / **개선이 필요한 점** — 각각 불릿 2~5개
4. **교사에게 제안** — 다음 수업·운영에서 할 수 있는 구체적 행동 3~6개
5. 데이터가 부족한 부분은 '추후 퀴즈·영상 위치 로그 연동 시 보강 가능' 정도로 짧게 언급할 수 있다.
"""
    return _generate(prompt)


def draft_operator_feedback_to_teacher(
    *,
    course_name: str,
    n_students: int,
    weeks_summary_block: str,
    questions_digest: str,
) -> str:
    """
    운영자 화면 — 집계 데이터를 바탕으로 담당 교사에게 보낼 피드백 **초안** (편집 가능하도록 마크다운).
    """
    prompt = f"""당신은 교육기관 **운영자**의 입장에서, 아래 집계를 참고해 담당 **교사**에게 전달할 피드백 **초안**을 작성한다.

[수업명] {course_name}
[배정 학생 수] {n_students}명

[주차별 집계 요약]
{weeks_summary_block[:10000]}

[학생 AI 질문 요약 — 일부]
{questions_digest[:8000]}

작성 규칙:
- **한국어**, 존댓말·격식을 갖추되 과하지 않게.
- 운영자 → 교사: 수업 운영·참여·질문 패턴에서 보이는 점을 **긍정과 함께** 개선·협력 제안을 2~4가지로 구체적으로.
- 확정 진단·비난·감정적 표현은 피하고, **데이터에 근거한 관찰**임을 전제로 쓴다.
- 분량은 대략 **400~900자** (마크다운 불릿·짧은 문단 허용).
- 출력은 **피드백 본문만** (서두 인사 한 줄 정도는 가능).

초안:
"""
    return _generate(prompt)


def analyze_student_learning_profile(
    *,
    student_display_name: str,
    course_name: str,
    weeks_lines: str,
    questions_block: str,
    total_questions: int,
    quiz_summary_block: str = "",
) -> str:
    """
    교사 화면 — 한 학생의 주차별 진행·질문 이력과 퀴즈(제출 시 저장된 요약)를 바탕으로 분석한다.
    """
    qb = (quiz_summary_block or "").strip()
    if not qb:
        qb = "(이 수업에 퀴즈 제출 기록이 없거나, 아직 저장된 퀴즈 요약이 없습니다.)"
    quiz_instruction = (
        "아래 [퀴즈·평가 요약]에 제출 기록이 있으면 **정답률·응시(재시도) 횟수·오답 문항 경향**을 "
        "반드시 반영해 분석한다. 퀴즈만으로 단정하지 말고 질문·진행률과 함께 해석한다. "
        "요약이 비어 있거나 제출 없음이면 퀴즈는 짧게 언급하거나 생략한다."
    )
    prompt = f"""당신은 교육 데이터를 해석하는 조교입니다. 아래는 한 학생이 **한 수업**에서 남긴 통계, 질문 기록, 퀴즈 요약입니다.
{quiz_instruction}

[학생 이름] {student_display_name}
[수업명] {course_name}
[이 수업에서 남긴 AI 질문 총 개수] {total_questions}건

[주차별 요약 — 제목, 시청 진행률(%), 해당 주차 질문 수]
{weeks_lines[:8000]}

[퀴즈·평가 요약 — 주차별, 마지막 제출 기준(정답/전체, 응시 횟수, 합격 여부, 오답 문항 번호·지문 일부)]
{qb[:12000]}

[질문 내용 일부 — 시간순 또는 최근 위주, 너무 길면 잘림]
{questions_block[:14000]}

요구사항 (한국어, 마크다운):
1. **전체 요약** (3~6문장): 이 학생의 학습 참여 패턴을 객관적으로 요약한다. 퀴즈 데이터가 있으면 성취·재시도 패턴을 한두 문장에 녹인다.
2. **잘하는 점 / 강점** — 불릿 2~5개 (질문 내용·진행률·참여도·퀴즈에서 근거를 짧게)
3. **보완이 필요한 점 / 약점** — 불릿 2~5개 (오답이 반복되는 주제가 있으면 구체적으로)
4. **교사가 도울 수 있는 제안** — 불릿 2~4개 (구체적으로)
5. 개인을 비하하거나 확정적 진단을 하지 말고, **관찰된 데이터에 기반**해 쓴다.
"""
    return _generate(prompt)


def answer_student_lesson_question(
    *,
    question: str,
    title: str,
    learning_goals: str,
    summary: str,
    keywords: str,
) -> str:
    """학생 수강 화면 — 주차 맥락만으로 질문에 답한다."""
    prompt = f"""당신은 교육용 AI 튜터입니다. 아래 [수업 맥락]에 근거해 학생 질문에만 답하세요.
맥락에 없는 내용은 추측하지 말고, 짧게 "이번 주차 자료에는 나와 있지 않습니다"라고 안내하세요.

[주차 제목] {title}

[학습 목표]
{learning_goals or "(없음)"}

[수업 요약·핵심]
{summary or "(없음)"}

[키워드]
{keywords or "(없음)"}

[학생 질문]
{question.strip()}

답변 요구: 한국어, 마크다운 사용 가능, 2~12문장 내로 간결하게."""
    return _generate(prompt)
