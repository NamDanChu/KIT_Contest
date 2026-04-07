"""요금제별 최대 학생(슬롯) 상한.

기획 `기획/EduChain_AI_전체정리.md` §5 요금제 표와 동일한 값을 사용합니다.
"""

from __future__ import annotations

# 기획: Starter 무료 체험 5명, Pro 50명, Premium 150명
PLAN_MAX_SLOTS: dict[str, int] = {
    "Starter": 5,
    "Pro": 50,
    "Premium": 150,
}

PLAN_ORDER: tuple[str, ...] = ("Starter", "Pro", "Premium")

# 이전 UI에서 저장된 문서 호환
_LEGACY_PLAN = {"Enterprise": "Premium"}


def normalize_plan(plan: str) -> str:
    """Firestore `plan` 값을 현재 요금제 키로 맞춘다."""
    p = (plan or "").strip()
    if p in _LEGACY_PLAN:
        return _LEGACY_PLAN[p]
    if p in PLAN_ORDER:
        return p
    return "Starter"


def max_slots_for_plan(plan: str) -> int:
    return PLAN_MAX_SLOTS.get(normalize_plan(plan), PLAN_MAX_SLOTS["Starter"])
