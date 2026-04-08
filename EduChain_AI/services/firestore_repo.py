"""Cloud Firestore — Organizations / Users / ChatLogs CRUD.

기획서 필드명과 맞춤. Admin SDK 사용 시 Firestore 보안 규칙은 적용되지 않음(서버 전용).

학생 AI 질문: Organizations/{org_id}/ContentCategories/{cat_id}/StudentLessonQuestions
"""

from __future__ import annotations

import re
import secrets
import string
from typing import Any, Literal

from firebase_admin import firestore

from .firebase_app import get_firestore_client
from .plan_limits import max_slots_for_plan

COL_ORGS = "Organizations"
COL_USERS = "Users"
COL_CHAT = "ChatLogs"
# Organizations/{org_id}/JoinRequests/{uid} — 초대 코드 소속 **승인 대기** (운영자 승인 후 Users 반영)
SUB_ORG_JOIN_REQUESTS = "JoinRequests"
# Organizations/{org_id}/ContentCategories/{category_id}
SUB_CONTENT_CATEGORIES = "ContentCategories"
# .../ContentCategories/{category_id}/LessonWeeks/{week_doc_id}
SUB_LESSON_WEEKS = "LessonWeeks"
# Users/{uid}/LessonProgress/{doc_id} — 학생별 주차 시청 진행률(0~100)
SUB_LESSON_PROGRESS = "LessonProgress"
# Organizations/{org_id}/ContentCategories/{cat_id}/StudentLessonQuestions/{doc_id}
SUB_STUDENT_LESSON_QUESTIONS = "StudentLessonQuestions"
# .../ContentCategories/{cat_id}/StudentIntegratedQuizLogs/{doc_id}
SUB_STUDENT_INTEGRATED_QUIZ_LOGS = "StudentIntegratedQuizLogs"
# Organizations/{org_id}/AiTokenRollup/{category_id | __org__} — Gemini 토큰 누적(버킷별)
SUB_AI_TOKEN_ROLLUP = "AiTokenRollup"
AI_ROLLUP_ORG_WIDE_ID = "__org__"
# Organizations/{org_id}/AiTokenEvents/{event_id} — 호출 1회당 로그(출처 추적)
SUB_AI_TOKEN_EVENTS = "AiTokenEvents"

# gemini_client / UI와 맞춤: 용도별 집계 키
AI_USAGE_BUCKETS: tuple[str, ...] = (
    "teacher_lesson",  # 수업 관리: 요약·퀴즈·노트·키워드 등
    "teacher_profile",  # 교사: 학생 학습 프로필 분석
    "teacher_course_stats",  # 교사: 수업 통계 AI 분석
    "student_chat",  # 학생: 주차 AI 질문/답변
    "student_quiz",  # 학생: 통합 퀴즈 코치·해설
    "operator",  # 운영: 교사 피드백 초안 등
)

# 세부 기능 집계 — AiTokenRollup 문서에 kind_{code}_prompt 등으로 누적 (표시용 한글 라벨)
AI_USAGE_KIND_LABELS_KO: dict[str, str] = {
    "lesson_summary_keywords": "수업 요약·키워드 (자료 학습)",
    "lesson_quiz_json": "객관식 퀴즈 풀 생성·저장",
    "lesson_quiz_markdown": "주차 퀴즈 (마크다운·TXT 배포)",
    "lesson_one_page_note": "한 페이지 요약 노트",
    "lesson_keywords_only": "키워드만 재추출",
    "student_week_ai_chat": "학생 수강·주차 AI 질문",
    "student_quiz_infinite_coach": "통합 퀴즈·무한 연습 코칭",
    "student_quiz_mixed_review": "통합 퀴즈·연습 후 AI 해설",
    "teacher_student_profile": "학생 학습 패턴 분석",
    "teacher_course_analysis": "수업 통계 AI (교사)",
    "operator_course_analysis": "수업 통계 AI (운영)",
    "operator_feedback_draft": "운영→교사 피드백 초안",
    "other": "기타·구버전 호출",
}


def get_organization(org_id: str) -> dict[str, Any] | None:
    if not org_id or not str(org_id).strip():
        return None
    db = get_firestore_client()
    snap = db.collection(COL_ORGS).document(org_id).get()
    if not snap.exists:
        return None
    return snap.to_dict()


def set_organization(
    org_id: str,
    org_name: str,
    max_slots: int,
    plan: str,
    owner_uid: str | None = None,
) -> None:
    db = get_firestore_client()
    data: dict[str, Any] = {
        "org_id": org_id,
        "org_name": org_name,
        "max_slots": max_slots,
        "plan": plan,
    }
    if owner_uid:
        data["owner_uid"] = owner_uid
    db.collection(COL_ORGS).document(org_id).set(data, merge=True)


def update_organization(
    org_id: str,
    *,
    org_name: str | None = None,
    max_slots: int | None = None,
    plan: str | None = None,
) -> None:
    """기업 필드 일부만 갱신."""
    db = get_firestore_client()
    ref = db.collection(COL_ORGS).document(org_id)
    data: dict[str, Any] = {}
    if org_name is not None:
        data["org_name"] = org_name
    if max_slots is not None:
        data["max_slots"] = int(max_slots)
    if plan is not None:
        data["plan"] = plan
    if not data:
        return
    ref.set(data, merge=True)


def create_organization(
    org_name: str,
    owner_uid: str,
    max_slots: int | None = None,
    plan: str = "Starter",
) -> str:
    """새 기업 문서 생성. 반환: org_id. `max_slots` 생략 시 `plan`에 맞는 상한(기획 표) 사용."""
    slots = int(max_slots) if max_slots is not None else max_slots_for_plan(plan)
    db = get_firestore_client()
    ref = db.collection(COL_ORGS).document()
    org_id = ref.id
    ref.set(
        {
            "org_id": org_id,
            "org_name": org_name,
            "max_slots": slots,
            "plan": plan,
            "owner_uid": owner_uid,
        }
    )
    return org_id


def list_organizations_by_owner(owner_uid: str) -> list[dict[str, Any]]:
    """운영자가 소유한 기업 목록."""
    db = get_firestore_client()
    q = db.collection(COL_ORGS).where("owner_uid", "==", owner_uid)
    out: list[dict[str, Any]] = []
    for doc in q.stream():
        d = doc.to_dict() or {}
        d["_doc_id"] = doc.id
        out.append(d)
    return out


def count_all_users() -> int:
    """전체 Users 문서 수 (첫 가입자 판별용)."""
    db = get_firestore_client()
    return sum(1 for _ in db.collection(COL_USERS).stream())


def get_user(uid: str) -> dict[str, Any] | None:
    db = get_firestore_client()
    snap = db.collection(COL_USERS).document(uid).get()
    if not snap.exists:
        return None
    return snap.to_dict()


def get_user_role(uid: str) -> str | None:
    user = get_user(uid)
    if not user:
        return None
    role = user.get("role")
    return str(role) if role is not None else None


def update_user_fields(
    uid: str,
    *,
    display_name: str | None = None,
    role: str | None = None,
) -> None:
    """Users 문서 일부 필드만 갱신(운영자 화면용)."""
    if not uid or not str(uid).strip():
        return
    db = get_firestore_client()
    ref = db.collection(COL_USERS).document(uid)
    patch: dict[str, Any] = {}
    if display_name is not None:
        patch["display_name"] = display_name
    if role is not None:
        patch["role"] = role
    if not patch:
        return
    ref.set(patch, merge=True)


def delete_user_document(uid: str) -> None:
    """Users 문서 삭제."""
    if not uid or not str(uid).strip():
        return
    db = get_firestore_client()
    db.collection(COL_USERS).document(uid).delete()


def upsert_user(
    uid: str,
    email: str,
    role: str,
    org_id: str | None,
    display_name: str | None = None,
) -> None:
    """가입·로그인 후 프로필 동기화. org_id 가 None 이면 아직 소속 기업 없음(운영자 등)."""
    db = get_firestore_client()
    data: dict[str, Any] = {
        "uid": uid,
        "email": email,
        "role": role,
    }
    if org_id is not None and str(org_id).strip():
        data["org_id"] = org_id
    else:
        data["org_id"] = None
    if display_name:
        data["display_name"] = display_name
    db.collection(COL_USERS).document(uid).set(data, merge=True)


def append_chat_log(uid: str, query: str, answer: str) -> str:
    """ChatLogs에 문서 추가. 반환값은 log_id."""
    db = get_firestore_client()
    ref = db.collection(COL_CHAT).document()
    ref.set(
        {
            "log_id": ref.id,
            "uid": uid,
            "query": query,
            "answer": answer,
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
    )
    return ref.id


def append_student_lesson_question(
    org_id: str,
    category_id: str,
    week_doc_id: str,
    student_uid: str,
    question: str,
    answer: str,
    *,
    week_title: str | None = None,
    week_index: int | None = None,
    student_email: str | None = None,
    display_name: str | None = None,
    video_position_sec: float | None = None,
    video_duration_sec: float | None = None,
) -> str:
    """수업·주차 맥락의 학생 AI 질문·답변을 저장. 교사 화면에서 조회.

    video_* 가 비어 있으면 ``Users/{uid}/LessonProgress`` 에 저장된
    ``last_video_position_sec`` / ``video_duration_sec`` 를 읽어 붙인다(영상 플레이어 연동).
    """
    if not org_id or not category_id or not week_doc_id or not student_uid:
        return ""
    pos_sec = _coerce_float_optional(video_position_sec)
    dur_sec = _coerce_float_optional(video_duration_sec)
    if pos_sec is None or dur_sec is None:
        snap = get_student_lesson_progress_fields(
            student_uid, org_id, category_id, week_doc_id
        )
        if pos_sec is None:
            pos_sec = snap.get("last_video_position_sec")
        if dur_sec is None:
            dur_sec = snap.get("video_duration_sec")
        pos_sec = _coerce_float_optional(pos_sec)
        dur_sec = _coerce_float_optional(dur_sec)
    label = _video_position_label_from_sec(pos_sec)
    db = get_firestore_client()
    ref = (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_CONTENT_CATEGORIES)
        .document(category_id)
        .collection(SUB_STUDENT_LESSON_QUESTIONS)
        .document()
    )
    q = (question or "").strip()
    a = (answer or "").strip()
    payload: dict[str, Any] = {
        "org_id": org_id,
        "category_id": category_id,
        "week_doc_id": week_doc_id,
        "week_title": (week_title or "").strip(),
        "week_index": int(week_index or 0),
        "student_uid": student_uid,
        "student_email": (student_email or "").strip(),
        "display_name": (display_name or "").strip(),
        "question": q[:8000],
        "answer": a[:16000],
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    if pos_sec is not None:
        payload["video_position_sec"] = pos_sec
    if dur_sec is not None:
        payload["video_duration_sec"] = dur_sec
    if label:
        payload["video_position_label"] = label
    ref.set(payload)
    return ref.id


def list_student_lesson_questions_for_course(
    org_id: str,
    category_id: str,
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """선택 수업(카테고리)에 대한 학생 AI 질문 로그. 최신순."""
    if not org_id or not category_id:
        return []
    lim = max(1, min(500, int(limit)))
    db = get_firestore_client()
    col = (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_CONTENT_CATEGORIES)
        .document(category_id)
        .collection(SUB_STUDENT_LESSON_QUESTIONS)
    )
    rows: list[dict[str, Any]] = []
    for doc in col.stream():
        d = doc.to_dict() or {}
        d["_doc_id"] = doc.id
        rows.append(d)

    def _ts_key(x: dict[str, Any]) -> float:
        ts = x.get("created_at")
        if ts is None:
            return 0.0
        try:
            if hasattr(ts, "timestamp"):
                return float(ts.timestamp())
        except (TypeError, ValueError, OSError):
            pass
        try:
            return float(ts)
        except (TypeError, ValueError):
            return 0.0

    rows.sort(key=_ts_key, reverse=True)
    return rows[:lim]


def list_student_lesson_questions_for_course_student(
    org_id: str,
    category_id: str,
    student_uid: str,
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """한 학생이 해당 수업에서 남긴 AI 질문만 (최신순 상한)."""
    if not student_uid:
        return []
    lim = max(1, min(500, int(limit)))
    rows = list_student_lesson_questions_for_course(org_id, category_id, limit=500)
    out = [r for r in rows if str(r.get("student_uid") or "") == str(student_uid)]
    return out[:lim]


def append_student_integrated_quiz_log(
    org_id: str,
    category_id: str,
    student_uid: str,
    *,
    course_name: str,
    event_type: str,
    details: dict[str, Any],
    student_email: str | None = None,
    display_name: str | None = None,
) -> str:
    """통합 퀴즈(일괄·무한 연습) 활동을 저장. 정식 주차 퀴즈 제출과 별도."""
    if not org_id or not category_id or not student_uid:
        return ""
    et = (event_type or "").strip() or "unknown"
    db = get_firestore_client()
    ref = (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_CONTENT_CATEGORIES)
        .document(category_id)
        .collection(SUB_STUDENT_INTEGRATED_QUIZ_LOGS)
        .document()
    )
    payload: dict[str, Any] = {
        "org_id": org_id,
        "category_id": category_id,
        "course_name": (course_name or "").strip()[:500],
        "student_uid": student_uid,
        "student_email": (student_email or "").strip(),
        "display_name": (display_name or "").strip(),
        "event_type": et[:120],
        "details": details or {},
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    ref.set(payload)
    return ref.id


def list_student_integrated_quiz_logs_for_course_student(
    org_id: str,
    category_id: str,
    student_uid: str,
    *,
    limit: int = 150,
) -> list[dict[str, Any]]:
    """한 학생의 통합 퀴즈 연습 로그(최신순)."""
    if not org_id or not category_id or not student_uid:
        return []
    lim = max(1, min(500, int(limit)))
    db = get_firestore_client()
    col = (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_CONTENT_CATEGORIES)
        .document(category_id)
        .collection(SUB_STUDENT_INTEGRATED_QUIZ_LOGS)
    )
    rows: list[dict[str, Any]] = []
    for doc in col.stream():
        d = doc.to_dict() or {}
        if str(d.get("student_uid") or "") != str(student_uid):
            continue
        d["_doc_id"] = doc.id
        rows.append(d)

    def _ts_key(x: dict[str, Any]) -> float:
        ts = x.get("created_at")
        if ts is None:
            return 0.0
        try:
            if hasattr(ts, "timestamp"):
                return float(ts.timestamp())
        except (TypeError, ValueError, OSError):
            pass
        try:
            return float(ts)
        except (TypeError, ValueError):
            return 0.0

    rows.sort(key=_ts_key, reverse=True)
    return rows[:lim]


def summarize_org_learning_snapshot(org_id: str) -> dict[str, Any]:
    """운영자 대시보드용 — 기업 단위 과목 수·인원·누적 AI 질문 건수(과목별 상한 500건 합산)."""
    out: dict[str, Any] = {
        "n_categories": 0,
        "n_teachers": 0,
        "n_students": 0,
        "total_ai_questions": 0,
    }
    if not org_id:
        return out
    users = list_users_by_org(org_id)
    out["n_teachers"] = sum(1 for u in users if str(u.get("role") or "") == "Teacher")
    out["n_students"] = sum(1 for u in users if str(u.get("role") or "") == "Student")
    cats = list_content_categories(org_id)
    out["n_categories"] = len(cats)
    total_q = 0
    for c in cats:
        cid = str(c.get("_doc_id") or "")
        if cid:
            total_q += len(
                list_student_lesson_questions_for_course(org_id, cid, limit=500)
            )
    out["total_ai_questions"] = total_q
    return out


def count_users_by_org(org_id: str) -> int:
    """동일 org_id 사용자 수(데모·운영자 화면용)."""
    db = get_firestore_client()
    q = db.collection(COL_USERS).where("org_id", "==", org_id)
    return sum(1 for _ in q.stream())


def _random_invite_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def ensure_org_invite_codes(org_id: str) -> dict[str, str]:
    """기업 문서에 교사/학생 초대 코드가 없으면 생성해 저장하고 둘 다 반환."""
    o = get_organization(org_id)
    if not o:
        return {}
    db = get_firestore_client()
    ref = db.collection(COL_ORGS).document(org_id)
    tc = (o.get("invite_code_teacher") or "").strip()
    sc = (o.get("invite_code_student") or "").strip()
    patch: dict[str, Any] = {}
    if not tc:
        tc = _random_invite_code()
        patch["invite_code_teacher"] = tc
    if not sc:
        sc = _random_invite_code()
        patch["invite_code_student"] = sc
    if tc and sc and tc == sc:
        sc = _random_invite_code()
        patch["invite_code_student"] = sc
    if patch:
        ref.set(patch, merge=True)
    return {"teacher": tc, "student": sc}


def regenerate_org_invite_code(
    org_id: str, kind: Literal["teacher", "student"]
) -> str:
    """초대 코드 재발급. 반환: 새 코드."""
    code = _random_invite_code()
    field = (
        "invite_code_teacher" if kind == "teacher" else "invite_code_student"
    )
    db = get_firestore_client()
    db.collection(COL_ORGS).document(org_id).set({field: code}, merge=True)
    return code


def find_org_and_role_by_invite_code(code: str) -> tuple[str, str] | None:
    """초대 코드로 (org_id, Teacher|Student) 조회. 없으면 None."""
    raw = (code or "").strip().upper().replace(" ", "")
    if len(raw) < 4:
        return None
    db = get_firestore_client()
    for field, role in (
        ("invite_code_teacher", "Teacher"),
        ("invite_code_student", "Student"),
    ):
        for doc in db.collection(COL_ORGS).where(field, "==", raw).limit(1).stream():
            return (doc.id, role)
    return None


def count_students_in_org(org_id: str) -> int:
    """해당 기업 소속 Student 역할 수(슬롯 비교용)."""
    db = get_firestore_client()
    q = db.collection(COL_USERS).where("org_id", "==", org_id)
    n = 0
    for doc in q.stream():
        d = doc.to_dict() or {}
        if str(d.get("role") or "") == "Student":
            n += 1
    return n


def list_users_by_org(org_id: str) -> list[dict[str, Any]]:
    """기업 소속 Users (역할·이메일·표시명)."""
    db = get_firestore_client()
    q = db.collection(COL_USERS).where("org_id", "==", org_id)
    out: list[dict[str, Any]] = []
    for doc in q.stream():
        d = doc.to_dict() or {}
        d["_doc_id"] = doc.id
        out.append(d)
    out.sort(key=lambda x: (str(x.get("role", "")), str(x.get("email", ""))))
    return out


def list_pending_join_requests(org_id: str) -> list[dict[str, Any]]:
    """기업별 초대 소속 승인 대기 목록(최신순)."""
    if not org_id or not str(org_id).strip():
        return []
    db = get_firestore_client()
    col = (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_ORG_JOIN_REQUESTS)
    )
    rows: list[dict[str, Any]] = []
    for doc in col.stream():
        d = doc.to_dict() or {}
        if str(d.get("status") or "pending") != "pending":
            continue
        d["_doc_id"] = doc.id
        rows.append(d)

    def _ts_key(x: dict[str, Any]) -> float:
        ts = x.get("created_at")
        if ts is None:
            return 0.0
        try:
            if hasattr(ts, "timestamp"):
                return float(ts.timestamp())
        except (TypeError, ValueError, OSError):
            pass
        return 0.0

    rows.sort(key=_ts_key, reverse=True)
    return rows


def submit_org_join_request(
    uid: str,
    email: str,
    display_name: str,
    org_id: str,
    requested_role: str,
) -> None:
    """초대 코드로 소속을 **신청**만 저장. 승인 전까지 role 은 User 유지."""
    uid = str(uid).strip()
    org_id = str(org_id).strip()
    if not uid or not org_id:
        raise ValueError("uid 와 org_id 가 필요합니다.")
    rr = str(requested_role).strip()
    if rr not in ("Teacher", "Student"):
        raise ValueError("requested_role 은 Teacher 또는 Student 여야 합니다.")
    db = get_firestore_client()
    prof = get_user(uid)
    if prof:
        old_org = str(prof.get("pending_org_id") or "").strip()
        if prof.get("membership_pending") and old_org and old_org != org_id:
            db.collection(COL_ORGS).document(old_org).collection(
                SUB_ORG_JOIN_REQUESTS
            ).document(uid).delete()

    req_ref = (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_ORG_JOIN_REQUESTS)
        .document(uid)
    )
    req_ref.set(
        {
            "uid": uid,
            "email": (email or "").strip(),
            "display_name": (display_name or "").strip(),
            "requested_role": rr,
            "status": "pending",
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )
    uref = db.collection(COL_USERS).document(uid)
    uref.set(
        {
            "uid": uid,
            "email": (email or "").strip(),
            "display_name": (display_name or "").strip(),
            "role": "User",
            "org_id": None,
            "membership_pending": True,
            "pending_org_id": org_id,
            "pending_role": rr,
        },
        merge=True,
    )


def approve_org_join_request(org_id: str, uid: str) -> None:
    """운영자 승인: User → Teacher/Student 반영, JoinRequests 문서 삭제."""
    org_id = str(org_id).strip()
    uid = str(uid).strip()
    if not org_id or not uid:
        raise ValueError("org_id 와 uid 가 필요합니다.")
    db = get_firestore_client()
    req_ref = (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_ORG_JOIN_REQUESTS)
        .document(uid)
    )
    req_snap = req_ref.get()
    if not req_snap.exists:
        raise RuntimeError("승인할 요청이 없습니다.")
    req = req_snap.to_dict() or {}
    role = str(req.get("requested_role") or "").strip()
    if role not in ("Teacher", "Student"):
        raise RuntimeError("요청 역할이 올바르지 않습니다.")
    prof = get_user(uid)
    if not prof:
        raise RuntimeError("사용자를 찾을 수 없습니다.")
    if str(prof.get("pending_org_id") or "").strip() != org_id:
        raise RuntimeError("사용자의 대기 요청이 이 기업과 일치하지 않습니다.")
    email = str(prof.get("email") or "")
    display_name = str(prof.get("display_name") or "").strip() or (
        email.split("@")[0] if email else "사용자"
    )
    org = get_organization(org_id)
    if not org:
        raise RuntimeError("기업을 찾을 수 없습니다.")
    if role == "Student":
        max_slots = int(org.get("max_slots") or 0)
        if count_students_in_org(org_id) >= max_slots:
            raise RuntimeError(
                "학생 슬롯이 가득 찼습니다. 승인할 수 없습니다. (슬롯을 늘리거나 다른 학생을 조정하세요.)"
            )
    upsert_user(uid, email, role, org_id, display_name=display_name)
    uref = db.collection(COL_USERS).document(uid)
    uref.set(
        {
            "membership_pending": False,
            "pending_org_id": None,
            "pending_role": None,
        },
        merge=True,
    )
    req_ref.delete()


def reject_org_join_request(org_id: str, uid: str) -> None:
    """운영자 거절: JoinRequests 삭제, 사용자는 User 로 유지."""
    org_id = str(org_id).strip()
    uid = str(uid).strip()
    if not org_id or not uid:
        raise ValueError("org_id 와 uid 가 필요합니다.")
    db = get_firestore_client()
    req_ref = (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_ORG_JOIN_REQUESTS)
        .document(uid)
    )
    if req_ref.get().exists:
        req_ref.delete()
    prof = get_user(uid)
    if prof and str(prof.get("pending_org_id") or "").strip() == org_id:
        db.collection(COL_USERS).document(uid).set(
            {
                "role": "User",
                "org_id": None,
                "membership_pending": False,
                "pending_org_id": None,
                "pending_role": None,
            },
            merge=True,
        )


def list_content_categories(org_id: str) -> list[dict[str, Any]]:
    """기업 소속 콘텐츠 카테고리(정렬 순)."""
    db = get_firestore_client()
    coll = (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_CONTENT_CATEGORIES)
    )
    out: list[dict[str, Any]] = []
    for doc in coll.stream():
        d = doc.to_dict() or {}
        d["_doc_id"] = doc.id
        out.append(d)
    out.sort(
        key=lambda x: (
            int(x.get("sort_order") or 0),
            str(x.get("name") or ""),
        )
    )
    return out


def get_content_category(org_id: str, category_id: str) -> dict[str, Any] | None:
    """단일 콘텐츠 카테고리 문서 (수강생 등 갱신 후 최신 조회용)."""
    if not org_id or not str(org_id).strip() or not category_id or not str(category_id).strip():
        return None
    db = get_firestore_client()
    snap = (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_CONTENT_CATEGORIES)
        .document(category_id)
        .get()
    )
    if not snap.exists:
        return None
    d = snap.to_dict() or {}
    d["_doc_id"] = snap.id
    return d


def list_content_categories_for_teacher(org_id: str, teacher_uid: str) -> list[dict[str, Any]]:
    """`teacher_uids`에 본인 UID가 포함된 콘텐츠 카테고리만 (정렬은 list_content_categories와 동일)."""
    if not org_id or not str(org_id).strip() or not teacher_uid:
        return []
    uid = str(teacher_uid).strip()
    out: list[dict[str, Any]] = []
    for c in list_content_categories(org_id):
        raw = c.get("teacher_uids") or []
        if not isinstance(raw, list):
            continue
        if uid in {str(x).strip() for x in raw if str(x).strip()}:
            out.append(c)
    return out


def list_content_categories_for_student(org_id: str, student_uid: str) -> list[dict[str, Any]]:
    """`student_uids`에 본인 UID가 포함된 콘텐츠 카테고리만."""
    if not org_id or not str(org_id).strip() or not student_uid:
        return []
    uid = str(student_uid).strip()
    out: list[dict[str, Any]] = []
    for c in list_content_categories(org_id):
        raw = c.get("student_uids") or []
        if not isinstance(raw, list):
            continue
        if uid in {str(x).strip() for x in raw if str(x).strip()}:
            out.append(c)
    return out


def normalize_category_sub_items(raw: Any) -> list[dict[str, str]]:
    """카테고리 하위 항목(교사 사이드바 드롭다운). ``id``, ``label``, ``icon``."""
    if not raw:
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for i, it in enumerate(raw):
        if not isinstance(it, dict):
            continue
        sid = str(it.get("id") or f"item_{i}").strip() or f"item_{i}"
        label = str(it.get("label") or "").strip() or "항목"
        icon = str(it.get("icon") or "📌").strip() or "📌"
        out.append({"id": sid, "label": label, "icon": icon})
    return out


def create_content_category(
    org_id: str,
    name: str,
    *,
    description: str = "",
) -> str:
    """콘텐츠 카테고리 생성. 반환: category_id (문서 ID).

    필드: ``name``, ``description``, ``sub_items``, ``sort_order``, ``teacher_uids``, ``student_uids``.
    """
    nm = (name or "").strip()
    if not nm:
        raise ValueError("카테고리 이름을 입력하세요.")
    desc = (description or "").strip()
    db = get_firestore_client()
    coll = (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_CONTENT_CATEGORIES)
    )
    n = sum(1 for _ in coll.stream())
    ref = coll.document()
    cat_id = ref.id
    ref.set(
        {
            "category_id": cat_id,
            "org_id": org_id,
            "name": nm,
            "description": desc,
            "sub_items": [],
            "sort_order": n,
            "teacher_uids": [],
            "student_uids": [],
        }
    )
    return cat_id


def update_content_category(
    org_id: str,
    category_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    teacher_overview: str | None = None,
    sub_items: list[dict[str, str]] | None = None,
    sort_order: int | None = None,
    teacher_uids: list[str] | None = None,
    student_uids: list[str] | None = None,
    operator_feedback_teacher: str | None = None,
    operator_feedback_student: str | None = None,
) -> None:
    """카테고리 이름·설명·교사 수업 개요·하위 항목·정렬·교사·수강생·운영자 피드백 갱신."""
    db = get_firestore_client()
    ref = (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_CONTENT_CATEGORIES)
        .document(category_id)
    )
    data: dict[str, Any] = {}
    if name is not None:
        data["name"] = (name or "").strip()
    if description is not None:
        data["description"] = (description or "").strip()
    if teacher_overview is not None:
        data["teacher_overview"] = (teacher_overview or "").strip()
    if sub_items is not None:
        data["sub_items"] = normalize_category_sub_items(sub_items)
    if sort_order is not None:
        data["sort_order"] = int(sort_order)
    if teacher_uids is not None:
        data["teacher_uids"] = [str(u) for u in teacher_uids if str(u).strip()]
    if student_uids is not None:
        data["student_uids"] = [str(u) for u in student_uids if str(u).strip()]
    if operator_feedback_teacher is not None:
        data["operator_feedback_teacher"] = (operator_feedback_teacher or "").strip()[:8000]
    if operator_feedback_student is not None:
        data["operator_feedback_student"] = (operator_feedback_student or "").strip()[:8000]
    if not data:
        return
    ref.set(data, merge=True)


def _lesson_weeks_coll(org_id: str, category_id: str):
    db = get_firestore_client()
    return (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_CONTENT_CATEGORIES)
        .document(category_id)
        .collection(SUB_LESSON_WEEKS)
    )


def list_lesson_weeks(org_id: str, category_id: str) -> list[dict[str, Any]]:
    """수업(카테고리) 하위 주차 문서 목록 (week_index 순)."""
    if not org_id or not category_id:
        return []
    coll = _lesson_weeks_coll(org_id, category_id)
    out: list[dict[str, Any]] = []
    for doc in coll.stream():
        d = doc.to_dict() or {}
        d["_doc_id"] = doc.id
        out.append(d)
    out.sort(key=lambda x: int(x.get("week_index") or 0))
    return out


def ensure_lesson_week_indices_contiguous(org_id: str, category_id: str) -> int:
    """
    week_index가 1..N이 아니면 목록 정렬 순서대로 1부터 다시 매긴다.
    (기존 데이터/수동 편집으로 2부터 시작하는 등 꼬인 경우 교정)
    반환: 변경된 문서 수.
    """
    weeks = list_lesson_weeks(org_id, category_id)
    if not weeks:
        return 0
    changed = 0
    for i, w in enumerate(weeks, start=1):
        wid = str(w.get("_doc_id") or "").strip()
        if not wid:
            continue
        cur = int(w.get("week_index") or 0)
        if cur != i:
            update_lesson_week(org_id, category_id, wid, week_index=i)
            changed += 1
    return changed


def get_lesson_week(
    org_id: str, category_id: str, week_doc_id: str
) -> dict[str, Any] | None:
    if not week_doc_id or not str(week_doc_id).strip():
        return None
    snap = _lesson_weeks_coll(org_id, category_id).document(week_doc_id).get()
    if not snap.exists:
        return None
    d = snap.to_dict() or {}
    d["_doc_id"] = snap.id
    return d


def ensure_lesson_weeks_seeded(
    org_id: str,
    category_id: str,
    *,
    default_weeks: int = 3,
) -> None:
    """주차 문서가 없으면 1~N주차 골격을 만든다."""
    coll = _lesson_weeks_coll(org_id, category_id)
    has_docs = False
    for _ in coll.limit(1).stream():
        has_docs = True
        break
    if has_docs:
        return
    for i in range(1, default_weeks + 1):
        coll.document(f"w{i}").set(
            {
                "week_index": i,
                "title": f"{i}주차",
                "learning_goals": "",
                "ai_summary_preview": "",
                "rag_sync_status": "idle",
                "uploads_meta": [],
                "keywords_extracted": "",
                "ai_quiz_markdown": "",
                "ai_quiz_num_questions": 0,
                "ai_one_page_note": "",
                # off | open_anytime | after_video
                "quiz_mode": "off",
                "quiz_source": "manual",
                "quiz_item_count": 10,
                "quiz_pass_min": 8,
                "quiz_manual_items": [],
                "quiz_ai_items": [],
                "org_id": org_id,
                "category_id": category_id,
                # open | scheduled | inactive(표시·수강불가) | disabled(숨김)
                "access_mode": "open",
                "window_start_iso": "",
                "window_end_iso": "",
                "lesson_video_url": "",
                "live_session_active": False,
            }
        )


def _default_lesson_week_payload(
    org_id: str, category_id: str, week_index: int, title: str
) -> dict[str, Any]:
    return {
        "week_index": week_index,
        "title": title,
        "learning_goals": "",
        "ai_summary_preview": "",
        "rag_sync_status": "idle",
        "uploads_meta": [],
        "keywords_extracted": "",
        "ai_quiz_markdown": "",
        "ai_quiz_num_questions": 0,
        "ai_one_page_note": "",
        "quiz_mode": "off",
        "quiz_source": "manual",
        "quiz_item_count": 10,
        "quiz_pass_min": 8,
        "quiz_manual_items": [],
        "quiz_ai_items": [],
        "org_id": org_id,
        "category_id": category_id,
        "access_mode": "open",
        "window_start_iso": "",
        "window_end_iso": "",
        "lesson_video_url": "",
        "live_session_active": False,
    }


def create_lesson_week(
    org_id: str,
    category_id: str,
    *,
    title: str | None = None,
) -> str:
    """새 주차 문서를 추가하고 문서 ID를 반환한다 (기존 week_index 최댓값 + 1)."""
    weeks = list_lesson_weeks(org_id, category_id)
    max_idx = max((int(w.get("week_index") or 0) for w in weeks), default=0)
    next_idx = max_idx + 1
    t = (title or "").strip() or f"{next_idx}주차"
    coll = _lesson_weeks_coll(org_id, category_id)
    new_ref = coll.document()
    new_ref.set(_default_lesson_week_payload(org_id, category_id, next_idx, t))
    return new_ref.id


def delete_lesson_week(org_id: str, category_id: str, week_doc_id: str) -> None:
    """주차 문서 삭제."""
    if not week_doc_id or not str(week_doc_id).strip():
        return
    _lesson_weeks_coll(org_id, category_id).document(week_doc_id).delete()


def update_lesson_week(
    org_id: str,
    category_id: str,
    week_doc_id: str,
    *,
    week_index: int | None = None,
    title: str | None = None,
    learning_goals: str | None = None,
    ai_summary_preview: str | None = None,
    rag_sync_status: str | None = None,
    uploads_meta: list[dict[str, Any]] | None = None,
    keywords_extracted: str | None = None,
    ai_quiz_markdown: str | None = None,
    ai_quiz_num_questions: int | None = None,
    ai_one_page_note: str | None = None,
    access_mode: str | None = None,
    window_start_iso: str | None = None,
    window_end_iso: str | None = None,
    lesson_video_url: str | None = None,
    live_session_active: bool | None = None,
    quiz_mode: str | None = None,
    quiz_source: str | None = None,
    quiz_item_count: int | None = None,
    quiz_pass_min: int | None = None,
    quiz_manual_items: list[dict[str, Any]] | None = None,
    quiz_ai_items: list[dict[str, Any]] | None = None,
) -> None:
    """주차별 수업 설계·RAG 메타·공개 설정 갱신."""
    ref = _lesson_weeks_coll(org_id, category_id).document(week_doc_id)
    data: dict[str, Any] = {}
    if week_index is not None:
        data["week_index"] = int(week_index)
    if title is not None:
        data["title"] = (title or "").strip() or "주차"
    if learning_goals is not None:
        data["learning_goals"] = (learning_goals or "").strip()
    if ai_summary_preview is not None:
        data["ai_summary_preview"] = (ai_summary_preview or "").strip()
    if rag_sync_status is not None:
        data["rag_sync_status"] = str(rag_sync_status).strip()
    if uploads_meta is not None:
        data["uploads_meta"] = uploads_meta
    if keywords_extracted is not None:
        data["keywords_extracted"] = (keywords_extracted or "").strip()
    if ai_quiz_markdown is not None:
        data["ai_quiz_markdown"] = (ai_quiz_markdown or "").strip()
    if ai_quiz_num_questions is not None:
        data["ai_quiz_num_questions"] = int(ai_quiz_num_questions)
    if ai_one_page_note is not None:
        data["ai_one_page_note"] = (ai_one_page_note or "").strip()
    if access_mode is not None:
        data["access_mode"] = str(access_mode).strip()
    if window_start_iso is not None:
        data["window_start_iso"] = str(window_start_iso or "").strip()
    if window_end_iso is not None:
        data["window_end_iso"] = str(window_end_iso or "").strip()
    if lesson_video_url is not None:
        data["lesson_video_url"] = str(lesson_video_url or "").strip()
    if live_session_active is not None:
        data["live_session_active"] = bool(live_session_active)
    if quiz_mode is not None:
        data["quiz_mode"] = str(quiz_mode).strip()
    if quiz_source is not None:
        data["quiz_source"] = str(quiz_source).strip()
    if quiz_item_count is not None:
        data["quiz_item_count"] = int(quiz_item_count)
    if quiz_pass_min is not None:
        data["quiz_pass_min"] = int(quiz_pass_min)
    if quiz_manual_items is not None:
        data["quiz_manual_items"] = quiz_manual_items
    if quiz_ai_items is not None:
        data["quiz_ai_items"] = quiz_ai_items
    if not data:
        return
    ref.set(data, merge=True)


def _lesson_progress_doc_id(org_id: str, category_id: str, week_doc_id: str) -> str:
    raw = f"{org_id}_{category_id}_{week_doc_id}"
    safe = re.sub(r"[^\w\-]+", "_", raw)
    return (safe[:120] or "lp")[:120]


def get_lesson_progress_doc_id(org_id: str, category_id: str, week_doc_id: str) -> str:
    """``Users/{uid}/LessonProgress/{doc_id}`` 문서 ID (클라이언트 자동 저장과 동일 규칙)."""
    return _lesson_progress_doc_id(org_id, category_id, week_doc_id)


def get_student_lesson_progress_percent(
    uid: str, org_id: str, category_id: str, week_doc_id: str
) -> int:
    """학생·수업·주차별 저장된 시청 진행률(0~100). 없으면 0."""
    if not uid or not org_id or not category_id or not week_doc_id:
        return 0
    db = get_firestore_client()
    doc_id = _lesson_progress_doc_id(org_id, category_id, week_doc_id)
    snap = (
        db.collection(COL_USERS)
        .document(uid)
        .collection(SUB_LESSON_PROGRESS)
        .document(doc_id)
        .get()
    )
    if not snap.exists:
        return 0
    d = snap.to_dict() or {}
    try:
        p = int(d.get("progress_percent") or 0)
    except (TypeError, ValueError):
        p = 0
    return max(0, min(100, p))


def _coerce_float_optional(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f < 0:
        return None
    return f


def get_student_lesson_progress_fields(
    uid: str, org_id: str, category_id: str, week_doc_id: str
) -> dict[str, Any]:
    """Users/{uid}/LessonProgress — 시청 %, 영상 재생 위치(초) 등 스냅샷."""
    out: dict[str, Any] = {
        "progress_percent": 0,
        "last_video_position_sec": None,
        "video_duration_sec": None,
        "quiz_passed": False,
        "quiz_correct": 0,
        "quiz_total": 0,
        "quiz_attempt_count": 0,
        "quiz_wrong_indices": [],
        "quiz_wrong_count": 0,
        "quiz_pool_indices": [],
    }
    if not uid or not org_id or not category_id or not week_doc_id:
        return out
    db = get_firestore_client()
    doc_id = _lesson_progress_doc_id(org_id, category_id, week_doc_id)
    snap = (
        db.collection(COL_USERS)
        .document(uid)
        .collection(SUB_LESSON_PROGRESS)
        .document(doc_id)
        .get()
    )
    if not snap.exists:
        return out
    d = snap.to_dict() or {}
    try:
        p = int(d.get("progress_percent") or 0)
    except (TypeError, ValueError):
        p = 0
    out["progress_percent"] = max(0, min(100, p))
    out["last_video_position_sec"] = _coerce_float_optional(d.get("last_video_position_sec"))
    out["video_duration_sec"] = _coerce_float_optional(d.get("video_duration_sec"))
    out["quiz_passed"] = bool(d.get("quiz_passed"))
    try:
        out["quiz_correct"] = max(0, int(d.get("quiz_correct") or 0))
    except (TypeError, ValueError):
        out["quiz_correct"] = 0
    try:
        out["quiz_total"] = max(0, int(d.get("quiz_total") or 0))
    except (TypeError, ValueError):
        out["quiz_total"] = 0
    try:
        out["quiz_attempt_count"] = max(0, int(d.get("quiz_attempt_count") or 0))
    except (TypeError, ValueError):
        out["quiz_attempt_count"] = 0
    raw_wi = d.get("quiz_wrong_indices")
    wi_list: list[int] = []
    if isinstance(raw_wi, list):
        for x in raw_wi:
            try:
                ix = int(x)
                if 0 <= ix < 100:
                    wi_list.append(ix)
            except (TypeError, ValueError):
                pass
    out["quiz_wrong_indices"] = wi_list
    try:
        out["quiz_wrong_count"] = max(0, int(d.get("quiz_wrong_count") or len(wi_list)))
    except (TypeError, ValueError):
        out["quiz_wrong_count"] = len(wi_list)
    raw_pi = d.get("quiz_pool_indices")
    pi_list: list[int] = []
    if isinstance(raw_pi, list):
        for x in raw_pi:
            try:
                ix = int(x)
                if 0 <= ix < 100:
                    pi_list.append(ix)
            except (TypeError, ValueError):
                pass
    out["quiz_pool_indices"] = pi_list
    return out


def merge_student_lesson_quiz_result(
    uid: str,
    org_id: str,
    category_id: str,
    week_doc_id: str,
    *,
    quiz_correct: int,
    quiz_total: int,
    quiz_passed: bool,
    quiz_wrong_indices: list[int] | None = None,
    quiz_pool_indices: list[int] | None = None,
) -> None:
    """주차별 퀴즈 제출 결과를 LessonProgress에 merge. 제출마다 quiz_attempt_count 가산."""
    if not uid or not org_id or not category_id or not week_doc_id:
        return
    db = get_firestore_client()
    doc_id = _lesson_progress_doc_id(org_id, category_id, week_doc_id)
    ref = (
        db.collection(COL_USERS)
        .document(uid)
        .collection(SUB_LESSON_PROGRESS)
        .document(doc_id)
    )
    snap = ref.get()
    prev_att = 0
    if snap.exists:
        try:
            prev_att = int((snap.to_dict() or {}).get("quiz_attempt_count") or 0)
        except (TypeError, ValueError):
            prev_att = 0
    wi: list[int] = []
    if quiz_wrong_indices is not None:
        for x in quiz_wrong_indices:
            try:
                ix = int(x)
                if 0 <= ix < 100:
                    wi.append(ix)
            except (TypeError, ValueError):
                pass
    payload: dict[str, Any] = {
        "org_id": org_id,
        "category_id": category_id,
        "week_doc_id": week_doc_id,
        "quiz_correct": max(0, int(quiz_correct)),
        "quiz_total": max(0, int(quiz_total)),
        "quiz_passed": bool(quiz_passed),
        "quiz_attempt_count": prev_att + 1,
        "quiz_wrong_indices": wi,
        "quiz_wrong_count": len(wi),
        "quiz_updated_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if quiz_pool_indices is not None:
        pi: list[int] = []
        for x in quiz_pool_indices:
            try:
                ix = int(x)
                if 0 <= ix < 100:
                    pi.append(ix)
            except (TypeError, ValueError):
                pass
        payload["quiz_pool_indices"] = pi
    ref.set(
        payload,
        merge=True,
    )


def reset_student_lesson_quiz_progress(
    uid: str, org_id: str, category_id: str, week_doc_id: str
) -> None:
    """재시도용 — 해당 주차 퀴즈 제출 기록을 초기화한다."""
    if not uid or not org_id or not category_id or not week_doc_id:
        return
    db = get_firestore_client()
    doc_id = _lesson_progress_doc_id(org_id, category_id, week_doc_id)
    ref = (
        db.collection(COL_USERS)
        .document(uid)
        .collection(SUB_LESSON_PROGRESS)
        .document(doc_id)
    )
    ref.set(
        {
            "org_id": org_id,
            "category_id": category_id,
            "week_doc_id": week_doc_id,
            "quiz_correct": 0,
            "quiz_total": 0,
            "quiz_passed": False,
            "quiz_attempt_count": 0,
            "quiz_wrong_indices": [],
            "quiz_wrong_count": 0,
            "quiz_pool_indices": [],
            "quiz_updated_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def aggregate_quiz_stats_for_course(
    org_id: str,
    category_id: str,
    student_uids: list[str],
    weeks: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    수업 통계용 — 배정 학생·주차별 LessonProgress 퀴즈 필드 집계.

    반환:
      total_attempts: 응시(제출) 횟수 합
      n_submissions: (학생×주차) 중 마지막 제출이 있는 건수
      total_wrong: 마지막 제출 기준 오답 수 합 (total - correct)
      by_week: 주차 doc_id → attempts, submissions, wrong_sum, wrong_idx_counts(dict idx→명수)
    """
    from collections import Counter

    by_week: dict[str, dict[str, Any]] = {}
    for w in weeks:
        wid = str(w.get("_doc_id") or "")
        if not wid:
            continue
        by_week[wid] = {
            "attempts": 0,
            "submissions": 0,
            "wrong_sum": 0,
            "wrong_idx_counts": Counter(),
        }

    total_attempts = 0
    n_submissions = 0
    total_wrong = 0

    for uid in student_uids:
        for w in weeks:
            wid = str(w.get("_doc_id") or "")
            if not wid:
                continue
            prog = get_student_lesson_progress_fields(uid, org_id, category_id, wid)
            qt = int(prog.get("quiz_total") or 0)
            if qt <= 0:
                continue
            n_submissions += 1
            qc = int(prog.get("quiz_correct") or 0)
            att = int(prog.get("quiz_attempt_count") or 0)
            wrong_n = max(0, qt - qc)
            total_wrong += wrong_n
            total_attempts += att
            bucket = by_week.setdefault(
                wid,
                {
                    "attempts": 0,
                    "submissions": 0,
                    "wrong_sum": 0,
                    "wrong_idx_counts": Counter(),
                },
            )
            bucket["attempts"] += att
            bucket["submissions"] += 1
            bucket["wrong_sum"] += wrong_n
            for ix in prog.get("quiz_wrong_indices") or []:
                try:
                    bucket["wrong_idx_counts"][int(ix)] += 1
                except (TypeError, ValueError):
                    pass

    return {
        "total_attempts": total_attempts,
        "n_submissions": n_submissions,
        "total_wrong": total_wrong,
        "by_week": by_week,
    }


def _video_position_label_from_sec(sec: float | None) -> str:
    if sec is None:
        return ""
    try:
        s = float(sec)
    except (TypeError, ValueError):
        return ""
    if s < 0:
        return ""
    m = int(s // 60)
    ss = int(round(s % 60))
    if ss >= 60:
        m += 1
        ss = 0
    return f"{m}:{ss:02d}"


def set_student_lesson_progress_percent(
    uid: str,
    org_id: str,
    category_id: str,
    week_doc_id: str,
    *,
    progress_percent: int,
) -> None:
    """시청 진행률(0~100) 저장. 기존보다 낮은 값은 무시(되감기로 진행률이 깎이지 않게)."""
    if not uid or not org_id or not category_id or not week_doc_id:
        return
    prev = get_student_lesson_progress_percent(uid, org_id, category_id, week_doc_id)
    p = max(0, min(100, int(progress_percent)))
    p = max(prev, p)
    db = get_firestore_client()
    doc_id = _lesson_progress_doc_id(org_id, category_id, week_doc_id)
    ref = (
        db.collection(COL_USERS)
        .document(uid)
        .collection(SUB_LESSON_PROGRESS)
        .document(doc_id)
    )
    ref.set(
        {
            "org_id": org_id,
            "category_id": category_id,
            "week_doc_id": week_doc_id,
            "progress_percent": p,
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def delete_content_category(org_id: str, category_id: str) -> None:
    db = get_firestore_client()
    (
        db.collection(COL_ORGS)
        .document(org_id)
        .collection(SUB_CONTENT_CATEGORIES)
        .document(category_id)
        .delete()
    )


def normalize_ai_usage_bucket(raw: str) -> str:
    s = (raw or "").strip()
    if s in AI_USAGE_BUCKETS:
        return s
    return "teacher_lesson"


def normalize_usage_kind(raw: str | None) -> str | None:
    """세부 기능 코드. 미지정이면 None(구버전 호환). 알 수 없는 문자열은 other."""
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip().lower().replace("-", "_")
    if s in AI_USAGE_KIND_LABELS_KO:
        return s
    return "other"


def kind_metrics_from_rollup_doc(doc: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Rollup 문서의 kind_* 필드를 {코드: {prompt, completion, calls}} 로 묶는다."""
    codes: set[str] = set()
    for k in doc:
        if k.startswith("kind_") and k.endswith("_prompt"):
            codes.add(k[5:-7])
    out: dict[str, dict[str, int]] = {}
    for code in codes:
        p = int(doc.get(f"kind_{code}_prompt") or 0)
        c = int(doc.get(f"kind_{code}_completion") or 0)
        n = int(doc.get(f"kind_{code}_calls") or 0)
        if p or c or n:
            out[code] = {"prompt": p, "completion": c, "calls": n}
    return out


def aggregate_ai_usage_kinds_for_org(org_id: str) -> dict[str, dict[str, int]]:
    """기업 내 모든 수업·__org__ rollup을 합산한 세부 기능별 총계."""
    oid = (org_id or "").strip()
    merged: dict[str, dict[str, int]] = {}
    if not oid:
        return merged
    db = get_firestore_client()
    coll = (
        db.collection(COL_ORGS).document(oid).collection(SUB_AI_TOKEN_ROLLUP)
    )
    for snap in coll.stream():
        d = snap.to_dict() or {}
        for code, m in kind_metrics_from_rollup_doc(d).items():
            if code not in merged:
                merged[code] = {"prompt": 0, "completion": 0, "calls": 0}
            merged[code]["prompt"] += m["prompt"]
            merged[code]["completion"] += m["completion"]
            merged[code]["calls"] += m["calls"]
    return merged


def increment_ai_token_rollup(
    org_id: str,
    *,
    category_id: str | None,
    bucket: str,
    prompt_tokens: int,
    completion_tokens: int,
    model: str | None = None,
    usage_kind: str | None = None,
) -> None:
    """성공한 Gemini 호출 1회분을 버킷별로 누적한다."""
    oid = (org_id or "").strip()
    if not oid:
        return
    b = normalize_ai_usage_bucket(bucket)
    pt = max(0, int(prompt_tokens))
    ct = max(0, int(completion_tokens))
    if pt == 0 and ct == 0:
        return
    doc_id = (category_id or "").strip() or AI_ROLLUP_ORG_WIDE_ID
    db = get_firestore_client()
    ref = (
        db.collection(COL_ORGS)
        .document(oid)
        .collection(SUB_AI_TOKEN_ROLLUP)
        .document(doc_id)
    )
    patch: dict[str, Any] = {
        f"{b}_prompt": firestore.Increment(pt),
        f"{b}_completion": firestore.Increment(ct),
        f"{b}_calls": firestore.Increment(1),
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if model:
        patch[f"{b}_last_model"] = str(model)[:120]
    uk = normalize_usage_kind(usage_kind)
    if uk:
        prefix = f"kind_{uk}"
        patch[f"{prefix}_prompt"] = firestore.Increment(pt)
        patch[f"{prefix}_completion"] = firestore.Increment(ct)
        patch[f"{prefix}_calls"] = firestore.Increment(1)
        if model:
            patch[f"{prefix}_last_model"] = str(model)[:120]
    ref.set(patch, merge=True)


def get_ai_token_rollup_doc(org_id: str, category_id: str | None) -> dict[str, Any]:
    oid = (org_id or "").strip()
    if not oid:
        return {}
    doc_id = (category_id or "").strip() or AI_ROLLUP_ORG_WIDE_ID
    db = get_firestore_client()
    snap = (
        db.collection(COL_ORGS)
        .document(oid)
        .collection(SUB_AI_TOKEN_ROLLUP)
        .document(doc_id)
        .get()
    )
    if not snap.exists:
        return {}
    return dict(snap.to_dict() or {})


def aggregate_ai_usage_buckets_for_org(org_id: str) -> dict[str, dict[str, int]]:
    """기업 내 모든 AiTokenRollup 문서를 합산해 버킷별 총계를 만든다."""
    oid = (org_id or "").strip()
    out: dict[str, dict[str, int]] = {
        b: {"prompt": 0, "completion": 0, "calls": 0} for b in AI_USAGE_BUCKETS
    }
    if not oid:
        return out
    db = get_firestore_client()
    coll = (
        db.collection(COL_ORGS).document(oid).collection(SUB_AI_TOKEN_ROLLUP)
    )
    for snap in coll.stream():
        d = snap.to_dict() or {}
        for b in AI_USAGE_BUCKETS:
            out[b]["prompt"] += int(d.get(f"{b}_prompt") or 0)
            out[b]["completion"] += int(d.get(f"{b}_completion") or 0)
            out[b]["calls"] += int(d.get(f"{b}_calls") or 0)
    return out


def rollup_doc_ids_for_org(org_id: str) -> list[str]:
    oid = (org_id or "").strip()
    if not oid:
        return []
    db = get_firestore_client()
    coll = (
        db.collection(COL_ORGS).document(oid).collection(SUB_AI_TOKEN_ROLLUP)
    )
    return [s.id for s in coll.stream()]


def append_ai_token_event(
    org_id: str,
    *,
    category_id: str | None,
    bucket: str,
    prompt_tokens: int,
    completion_tokens: int,
    model: str | None = None,
    usage_kind: str | None = None,
    actor_uid: str | None = None,
    actor_role: str | None = None,
    actor_display_name: str | None = None,
) -> None:
    """Gemini 호출 1건을 이벤트로 남긴다(입·출력이 어떤 기능에서 발생했는지 추적)."""
    oid = (org_id or "").strip()
    if not oid:
        return
    b = normalize_ai_usage_bucket(bucket)
    pt = max(0, int(prompt_tokens))
    ct = max(0, int(completion_tokens))
    if pt == 0 and ct == 0:
        return
    cat_val: str | None = None
    if category_id and str(category_id).strip():
        cat_val = str(category_id).strip()
    db = get_firestore_client()
    ref = (
        db.collection(COL_ORGS)
        .document(oid)
        .collection(SUB_AI_TOKEN_EVENTS)
        .document()
    )
    uk = normalize_usage_kind(usage_kind)
    ev: dict[str, Any] = {
        "created_at": firestore.SERVER_TIMESTAMP,
        "category_id": cat_val,
        "bucket": b,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "model": (str(model)[:120] if model else ""),
    }
    if uk:
        ev["usage_kind"] = uk
    au = (actor_uid or "").strip()
    if au:
        ev["actor_uid"] = au
    ar = (actor_role or "").strip()
    if ar:
        ev["actor_role"] = ar
    adn = (actor_display_name or "").strip()
    if adn:
        ev["actor_display_name"] = adn
    ref.set(ev)


def list_recent_ai_token_events(org_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
    """최근 AI 토큰 이벤트(시간 역순). Firestore 단일 필드 정렬."""
    oid = (org_id or "").strip()
    if not oid:
        return []
    lim = max(1, min(2500, int(limit)))
    db = get_firestore_client()
    coll = (
        db.collection(COL_ORGS).document(oid).collection(SUB_AI_TOKEN_EVENTS)
    )
    try:
        from google.cloud.firestore_v1 import Query as FsQuery

        q = coll.order_by(
            "created_at",
            direction=FsQuery.DESCENDING,
        ).limit(lim)
        out: list[dict[str, Any]] = []
        for d in q.stream():
            row = dict(d.to_dict() or {})
            row["_doc_id"] = d.id
            out.append(row)
        return out
    except Exception:
        # 정렬 인덱스 미생성 등 — 최근 문서만 대략적으로 (문서 수가 적을 때)
        out = []
        for d in coll.limit(lim).stream():
            row = dict(d.to_dict() or {})
            row["_doc_id"] = d.id
            out.append(row)
        def _ts_key(v: Any) -> float:
            if v is None:
                return 0.0
            try:
                return float(v.timestamp())
            except Exception:
                return 0.0

        try:
            out.sort(key=lambda r: _ts_key(r.get("created_at")), reverse=True)
        except Exception:
            pass
        return out[:lim]
