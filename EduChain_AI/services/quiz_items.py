"""주차 퀴즈 — 4지선다 문항 정규화·세션 슬라이스."""

from __future__ import annotations

from typing import Any


def normalize_quiz_items(raw: Any) -> list[dict[str, Any]]:
    """JSON/Firestore에서 읽은 문항 배열을 정규화한다. 실패 시 ValueError."""
    if not isinstance(raw, list):
        raise ValueError("문항은 배열(JSON list)이어야 합니다.")
    out: list[dict[str, Any]] = []
    for it in raw:
        if not isinstance(it, dict):
            raise ValueError("각 문항은 객체여야 합니다.")
        text = str(it.get("text") or "").strip()
        opts = it.get("options")
        if not isinstance(opts, list) or len(opts) != 4:
            raise ValueError("각 문항은 보기(options) 4개가 필요합니다.")
        options = [str(x).strip() for x in opts]
        try:
            cor = int(it.get("correct", 0))
        except (TypeError, ValueError) as e:
            raise ValueError("정답(correct)은 0~3 정수여야 합니다.") from e
        if cor not in (0, 1, 2, 3):
            raise ValueError("정답(correct)은 0~3 중 하나여야 합니다.")
        if not text:
            raise ValueError("문항 본문(text)이 비었습니다.")
        ex = str(it.get("explanation") or "").strip()
        row: dict[str, Any] = {"text": text, "options": options, "correct": cor}
        if ex:
            row["explanation"] = ex
        out.append(row)
    return out


def quiz_pool_for_week(week: dict[str, Any]) -> list[dict[str, Any]]:
    """quiz_source에 따라 저장된 문항 풀을 반환한다 (정규화 실패 시 빈 목록)."""
    src = str(week.get("quiz_source") or "manual")
    raw = (
        week.get("quiz_ai_items")
        if src == "gemini"
        else week.get("quiz_manual_items")
    )
    if not isinstance(raw, list):
        raw = []
    try:
        return normalize_quiz_items(raw)
    except ValueError:
        return []


def quiz_session_params(week: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """
    학생에게 낼 문항 목록과 통과에 필요한 정답 수를 반환한다.
    반환: (세션 문항, pass_min)
    """
    pool = quiz_pool_for_week(week)
    try:
        want = int(week.get("quiz_item_count") or 0)
    except (TypeError, ValueError):
        want = 0
    if want <= 0:
        want = len(pool) or 1
    want = max(1, min(50, want))
    session = pool[:want]
    try:
        pm = int(week.get("quiz_pass_min") or 0)
    except (TypeError, ValueError):
        pm = 0
    if pm <= 0:
        pm = len(session) or 1
    pm = max(1, min(len(session), pm)) if session else 0
    return session, pm
