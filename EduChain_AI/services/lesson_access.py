"""주차(LessonWeeks) 공개 설정 — 학생 화면에서 회차 노출 여부 판별."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _parse_iso_naive(s: str) -> datetime | None:
    if not s or not str(s).strip():
        return None
    try:
        return datetime.fromisoformat(str(s).strip())
    except Exception:
        return None


def week_access_label_short(week: dict[str, Any]) -> str:
    """교사·관리 화면 표용: 공개 설정 한 줄 요약."""
    mode = str(week.get("access_mode") or "open").strip()
    if mode == "disabled":
        return "숨김"
    if mode == "inactive":
        return "비활성(표시)"
    if mode == "open":
        return "제한 없음"
    if mode == "scheduled":
        return "기간 예약"
    return mode or "—"


def week_in_student_list(week: dict[str, Any]) -> bool:
    """학생 주차 목록에 노출할지. `disabled`(숨김)만 목록에서 제외."""
    mode = str(week.get("access_mode") or "open").strip()
    return mode != "disabled"


def week_is_visible_to_student(
    week: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """
    학생이 해당 회차를 **수강(열람·재생)** 할 수 있는지.

    Returns:
        (허용 여부, 비허용 시 사용자에게 보여줄 짧은 이유 — 허용이면 빈 문자열)
    """
    mode = str(week.get("access_mode") or "open").strip()
    if mode == "disabled":
        return False, "이 회차는 숨김 처리되어 목록에 표시되지 않습니다."

    if mode == "inactive":
        return False, "이 회차는 비활성화되어 수강을 시작할 수 없습니다."

    if mode == "open":
        return True, ""

    if mode != "scheduled":
        return True, ""

    now = now or datetime.now()
    wstart = _parse_iso_naive(str(week.get("window_start_iso") or ""))
    wend = _parse_iso_naive(str(week.get("window_end_iso") or ""))

    if not wstart:
        return False, "이 회차는 아직 공개 일정이 설정되지 않았습니다."

    if now < wstart:
        return False, f"이 회차는 {wstart.strftime('%Y-%m-%d %H:%M')} 부터 열립니다."

    if wend and now > wend:
        return False, f"이 회차 시청·열람 기간이 종료되었습니다. ({wend.strftime('%Y-%m-%d %H:%M')} 까지)"

    return True, ""
