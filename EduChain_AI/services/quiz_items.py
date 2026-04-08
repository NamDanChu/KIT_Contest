"""주차 퀴즈 — 4지선다 문항 정규화·풀에서 무작위 출제."""

from __future__ import annotations

import random
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


def quiz_want_count(week: dict[str, Any]) -> int:
    """한 번 응시에 출제할 문항 수(상한 50)."""
    pool = quiz_pool_for_week(week)
    try:
        want = int(week.get("quiz_item_count") or 0)
    except (TypeError, ValueError):
        want = 0
    if want <= 0:
        want = len(pool) or 1
    return max(1, min(50, want))


def draw_quiz_pool_indices(pool_len: int, want: int, rng: random.Random) -> list[int]:
    """
    풀(순서 고정)에서 want개를 무작위로 뽑은 인덱스 목록.
    ``pool[i]`` 로 복원해 동일 응시 세션을 재구성한다.
    """
    if pool_len <= 0:
        return []
    k = max(1, min(50, want))
    k = min(k, pool_len)
    return rng.sample(range(pool_len), k)


def quiz_pass_min_for_session(week: dict[str, Any], session_len: int) -> int:
    """통과에 필요한 정답 수 (세션 길이 이하로 클램프)."""
    if session_len <= 0:
        return 0
    try:
        pm = int(week.get("quiz_pass_min") or 0)
    except (TypeError, ValueError):
        pm = 0
    if pm <= 0:
        pm = session_len
    return max(1, min(session_len, pm))


def quiz_preview_session_pair(week: dict[str, Any]) -> tuple[int, int]:
    """
    주차 목록 등 미리보기용: (한 응시당 출제 문항 수, 통과 정답 수 기준).
    풀에서 무작위로 뽑으므로 **개수**만 안내한다.
    """
    pool = quiz_pool_for_week(week)
    if not pool:
        return 0, 0
    sl = min(quiz_want_count(week), len(pool))
    pm = quiz_pass_min_for_session(week, sl)
    return sl, pm


def quiz_session_params(week: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """
    학생에게 낼 문항 목록과 통과에 필요한 정답 수 (레거시·미리보기).

    풀 크기 > 출제 수일 때도 **항상 풀 앞쪽 슬라이스**를 반환한다
    (저장된 무작위 인덱스가 없을 때만 사용).
    """
    pool = quiz_pool_for_week(week)
    want = quiz_want_count(week)
    session = pool[: min(want, len(pool))]
    pm = quiz_pass_min_for_session(week, len(session))
    return session, pm


def parse_quiz_pool_indices_saved(raw: Any, pool_len: int) -> list[int]:
    """Firestore 등에서 읽은 quiz_pool_indices를 검증한다."""
    out: list[int] = []
    if not isinstance(raw, list):
        return out
    for x in raw:
        try:
            ix = int(x)
        except (TypeError, ValueError):
            continue
        if 0 <= ix < pool_len:
            out.append(ix)
    return out


def session_items_for_progress_review(
    week: dict[str, Any], prog: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    교사 화면·분석용: 제출 기록의 풀 인덱스로 실제 출제 문항을 복원한다.
    인덱스가 없거나 풀과 맞지 않으면 레거시(앞쪽 슬라이스)로 폴백한다.
    """
    pool = quiz_pool_for_week(week)
    if not pool:
        return []
    qt = int(prog.get("quiz_total") or 0)
    raw_ix = prog.get("quiz_pool_indices")
    idxs = parse_quiz_pool_indices_saved(raw_ix, len(pool))
    if idxs and qt > 0 and len(idxs) == qt:
        sess = [pool[i] for i in idxs]
        if len(sess) == qt:
            return sess
    session, _ = quiz_session_params(week)
    return session
