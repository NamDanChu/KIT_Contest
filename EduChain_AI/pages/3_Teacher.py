"""교사: 수업 선택 후 개요·학생 관리·수업 통계·수업 관리 전환 (탭은 사이드바)."""

from __future__ import annotations

import html as html_mod
from collections import Counter
from datetime import datetime
from typing import Any

import streamlit as st

from services.firestore_repo import (
    ensure_lesson_week_indices_contiguous,
    ensure_lesson_weeks_seeded,
    get_content_category,
    get_lesson_week,
    get_organization,
    get_student_lesson_progress_fields,
    get_student_lesson_progress_percent,
    get_user,
    list_content_categories_for_teacher,
    list_lesson_weeks,
    list_student_integrated_quiz_logs_for_course_student,
    list_student_lesson_questions_for_course,
    list_student_lesson_questions_for_course_student,
    list_users_by_org,
    update_content_category,
)
from services.quiz_items import session_items_for_progress_review
from services import gemini_client
from services import ui_messages
from services.ai_usage_ui import render_teacher_ai_usage_panel
from services.course_stats_ui import render_course_statistics_panel
from services.lesson_access import week_access_label_short
from services.lesson_mgmt_ui import render_lesson_management_panel
from services.plan_limits import normalize_plan
from services.sidebar_helpers import (
    get_teacher_category_sub_items,
    hide_login_nav_when_authed,
    render_login_gate_with_intro,
    render_sidebar_user_block,
    render_teacher_sidebar,
)
from services.session_keys import (
    AUTH_ORG_ID,
    AUTH_ORG_NAME,
    AUTH_ROLE,
    AUTH_UID,
    TEACHER_LESSON_FINGERPRINT,
    TEACHER_SELECTED_CATEGORY_ID,
    TEACHER_SELECTED_SUB_ITEM_ID,
    TEACHER_STUDENT_DETAIL_UID,
    TEACHER_VIEW_TAB,
)

hide_login_nav_when_authed()


def _fmt_question_ts(val: Any) -> str:
    if val is None:
        return "—"
    try:
        if hasattr(val, "strftime"):
            return val.strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    try:
        if hasattr(val, "timestamp"):
            return datetime.fromtimestamp(val.timestamp()).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    return str(val)


def _render_student_questions_scrollable(week_qs: list[dict[str, Any]], *, max_height_px: int = 400) -> None:
    """질문 목록이 길어질 때 스크롤 영역 유지."""
    if not week_qs:
        st.caption("(이 주차에 질문 기록이 없습니다.)")
        return
    parts: list[str] = []
    for r in week_qs:
        ts = _fmt_question_ts(r.get("created_at"))
        qv = html_mod.escape((r.get("question") or "").strip() or "—")
        vlab = (str(r.get("video_position_label") or "").strip())
        if not vlab and r.get("video_position_sec") is not None:
            try:
                s = float(r.get("video_position_sec"))
                m = int(s // 60)
                ss = int(round(s % 60))
                vlab = f"{m}:{ss:02d}"
            except (TypeError, ValueError):
                vlab = ""
        pos_line = (
            f"<div style='font-size:0.72rem;color:#555;margin:0.15rem 0 0.35rem 0;'>영상 위치: "
            f"{html_mod.escape(vlab or '— (미기록)')}</div>"
            if vlab or r.get("video_position_sec") is not None
            else ""
        )
        parts.append(
            f"<div style='margin-bottom:0.85rem;padding-bottom:0.65rem;border-bottom:1px solid rgba(49,51,63,0.12);'>"
            f"<div style='font-size:0.78rem;color:#666;margin-bottom:0.25rem;'>{html_mod.escape(ts)}</div>"
            f"{pos_line}"
            f"<div style='white-space:pre-wrap;'>{qv}</div></div>"
        )
    inner = "".join(parts)
    st.markdown(
        f'<div style="max-height:{max_height_px}px;overflow-y:auto;border:1px solid rgba(49,51,63,0.18);'
        f"border-radius:10px;padding:0.75rem 0.85rem;background:rgba(250,250,252,0.95);\">{inner}</div>",
        unsafe_allow_html=True,
    )


def _render_student_info_panel(
    *,
    org_id: str,
    category_id: str,
    course_name: str,
    student_uid: str,
    weeks: list[dict[str, Any]],
    display_name: str,
    email: str,
) -> None:
    """메인 화면 — 학생 통계(질문·퀴즈 예정) + 주차별 질문 + Gemini 학습 분석."""
    analysis_key = f"teacher_stu_analysis_md_{category_id}_{student_uid}"
    prof = get_user(student_uid) or {}
    h1, h2 = st.columns([4, 1])
    with h1:
        st.markdown(f"#### {display_name}")
    with h2:
        if st.button(
            "선택 해제",
            key=f"clear_stu_panel_{category_id}_{student_uid}",
            type="secondary",
        ):
            st.session_state.pop(TEACHER_STUDENT_DETAIL_UID, None)
            st.session_state.pop(analysis_key, None)
            st.rerun()

    st.caption(f"이메일: `{email or '—'}`")
    bday = (
        str(prof.get("birthday") or prof.get("date_of_birth") or prof.get("birth_date") or "")
        .strip()
    )
    if bday:
        st.caption(f"생일: **{bday}**")
    else:
        st.caption("생일: — (추후 `Users` 프로필 필드로 연동 가능)")

    st.markdown(f"##### 수업 · {course_name}")
    rows = list_student_lesson_questions_for_course_student(
        org_id, category_id, student_uid, limit=300
    )
    by_w = Counter(str(r.get("week_doc_id") or "") for r in rows)
    total_q = len(rows)

    st.markdown("##### 이 수업에서의 활동 통계")
    m1, m2 = st.columns(2)
    with m1:
        st.metric("AI 질문 누적", f"{total_q}건")
    with m2:
        st.caption("퀴즈 (이 수업·마지막 제출 기준 누적)")
        tot_att = 0
        tot_wrong = 0
        for w in weeks:
            wid0 = str(w.get("_doc_id") or "")
            if not wid0:
                continue
            pq0 = get_student_lesson_progress_fields(
                student_uid, org_id, category_id, wid0
            )
            qt0 = int(pq0.get("quiz_total") or 0)
            if qt0 <= 0:
                continue
            tot_att += int(pq0.get("quiz_attempt_count") or 0)
            tot_wrong += max(
                0,
                qt0 - int(pq0.get("quiz_correct") or 0),
            )
        if tot_att <= 0:
            st.caption("퀴즈 제출 기록이 없습니다.")
        else:
            st.metric("응시(제출) 횟수 합계", f"{tot_att}회")
            st.caption(f"오답 문항 수 합계: **{tot_wrong}**개 (주차별 상세는 아래 주차 선택)")

    if not weeks:
        st.info(
            "등록된 주차가 없습니다. **수업 관리**에서 주차를 추가하면 주차별 질문·진행률을 볼 수 있습니다."
        )
    else:
        st.caption(
            "아래에서 **주차**를 고르면, 그 주차에서 남긴 **질문**이 하단 스크롤 영역에 표시됩니다."
        )
        choice_ids: list[str] = []
        choice_labels: list[str] = []
        for w in weeks:
            wid = str(w.get("_doc_id") or "")
            wi = int(w.get("week_index") or 0)
            wt = str(w.get("title") or f"{wi}주차")
            qc = int(by_w.get(wid, 0))
            pct = get_student_lesson_progress_percent(student_uid, org_id, category_id, wid)
            pq_w = get_student_lesson_progress_fields(
                student_uid, org_id, category_id, wid
            )
            qt_w = int(pq_w.get("quiz_total") or 0)
            q_extra = ""
            if qt_w > 0:
                att_w = int(pq_w.get("quiz_attempt_count") or 0)
                wn_w = int(
                    pq_w.get("quiz_wrong_count")
                    or max(0, qt_w - int(pq_w.get("quiz_correct") or 0))
                )
                q_extra = f" · 퀴즈 제출 {att_w}회 · 오답 {wn_w}개"
            choice_ids.append(wid)
            choice_labels.append(f"{wt} · 질문 {qc}건 · 진행 {pct}%{q_extra}")

        ix = st.selectbox(
            "주차 선택",
            options=list(range(len(choice_ids))),
            format_func=lambda i: choice_labels[i],
            key=f"main_stu_week_{category_id}_{student_uid}",
        )
        sel_wid = choice_ids[ix]
        week_qs = [r for r in rows if str(r.get("week_doc_id") or "") == sel_wid]
        sel_week_title = choice_labels[ix].split(" · ")[0] if choice_labels else "—"
        st.markdown(f"##### {sel_week_title} — 질문 내역")
        _render_student_questions_scrollable(week_qs, max_height_px=400)

        st.markdown(f"##### {sel_week_title} — 퀴즈·오답")
        pq = get_student_lesson_progress_fields(
            student_uid, org_id, category_id, sel_wid
        )
        qt = int(pq.get("quiz_total") or 0)
        if qt <= 0:
            st.caption(
                "(이 주차에 퀴즈가 없거나 아직 제출 기록이 없습니다. 학생이 퀴즈를 제출하면 표시됩니다.)"
            )
        else:
            qc = int(pq.get("quiz_correct") or 0)
            att = int(pq.get("quiz_attempt_count") or 0)
            st.caption(
                f"마지막 제출 기준 · 정답 **{qc}** / **{qt}** · 응시 **{att}**회"
                + (" · 합격" if pq.get("quiz_passed") else " · 미합격(기준 미달 가능)")
            )
            week_doc = get_lesson_week(org_id, category_id, sel_wid) or {}
            session_items = session_items_for_progress_review(week_doc, pq)
            raw_ix = pq.get("quiz_wrong_indices") or []
            indices: list[int] = []
            for x in raw_ix:
                try:
                    ix = int(x)
                    if 0 <= ix < 100:
                        indices.append(ix)
                except (TypeError, ValueError):
                    pass
            indices = sorted(set(indices))
            if indices and session_items:
                st.markdown("**틀린 문항 (지문 일부)**")
                for idx in indices:
                    if idx < len(session_items):
                        ttxt = str(session_items[idx].get("text") or "").strip()
                        short = ttxt[:220] + ("…" if len(ttxt) > 220 else "")
                        st.caption(f"- 문항 **{idx + 1}**: {short}")
            elif qc >= qt:
                st.caption("마지막 제출에서 오답이 없습니다.")
            else:
                st.caption(
                    "(문항 텍스트를 불러오지 못했습니다. 수업 관리에서 해당 주차 퀴즈 문항을 확인하세요.)"
                )

    st.markdown("##### 통합 퀴즈(연습) 기록")
    st.caption(
        "학생이 **통합 퀴즈**에서 연습한 내용입니다. 정식 주차 퀴즈 제출·성적과는 별도로 저장됩니다."
    )
    iq_rows = list_student_integrated_quiz_logs_for_course_student(
        org_id, category_id, student_uid, limit=120
    )
    _et_mix = {
        "infinite_answer": "무한 연습 · 정답 확인",
        "infinite_session_end": "무한 연습 · 세션 종료",
        "batch_complete": "일괄 연습 · 채점 완료",
    }
    if not iq_rows:
        st.caption("(통합 퀴즈 연습 기록이 없습니다.)")
    else:
        st.caption(f"최근 **{len(iq_rows)}**건까지 표시합니다.")
        for r in iq_rows[:80]:
            et = str(r.get("event_type") or "")
            ts = _fmt_question_ts(r.get("created_at"))
            title = _et_mix.get(et, et or "기록")
            with st.expander(f"{ts} · {title}", expanded=False):
                st.json(r.get("details") or {})

    st.divider()
    st.markdown("##### AI 학습 분석")
    st.caption(
        "**질문 내용·주차별 진행률·퀴즈(제출 기록이 있는 경우)** 를 바탕으로 강점·보완점을 정리합니다."
    )

    def _build_analysis_payload() -> tuple[str, str, str]:
        lines: list[str] = []
        for w in weeks:
            wid = str(w.get("_doc_id") or "")
            wi = int(w.get("week_index") or 0)
            wt = str(w.get("title") or f"{wi}주차")
            qc = int(by_w.get(wid, 0))
            pct = get_student_lesson_progress_percent(student_uid, org_id, category_id, wid)
            lines.append(f"- {wt}: 시청 진행 {pct}%, 질문 {qc}건")
        weeks_lines = "\n".join(lines) if lines else "(없음)"
        q_parts: list[str] = []
        for r in rows[:100]:
            ts = _fmt_question_ts(r.get("created_at"))
            wt = (r.get("week_title") or "").strip() or "—"
            qv = (r.get("question") or "").strip() or "—"
            vlab = (r.get("video_position_label") or "").strip()
            vextra = f" | 영상:{vlab}" if vlab else ""
            q_parts.append(f"{ts} | 주차:{wt}{vextra} | {qv}")
        questions_block = "\n".join(q_parts) if q_parts else "(질문 기록 없음)"

        quiz_lines: list[str] = []
        for w in weeks:
            wid = str(w.get("_doc_id") or "").strip()
            if not wid:
                continue
            wi = int(w.get("week_index") or 0)
            wt = str(w.get("title") or f"{wi}주차")
            pq = get_student_lesson_progress_fields(
                student_uid, org_id, category_id, wid
            )
            qt = int(pq.get("quiz_total") or 0)
            if qt <= 0:
                continue
            qc = int(pq.get("quiz_correct") or 0)
            att = int(pq.get("quiz_attempt_count") or 0)
            passed = bool(pq.get("quiz_passed"))
            pass_lbl = "합격" if passed else "미합격(또는 기준 미달)"
            line = (
                f"- {wt}: 정답 {qc}/{qt}, 응시(제출) {att}회, {pass_lbl}"
            )
            week_doc = get_lesson_week(org_id, category_id, wid) or {}
            session_items = session_items_for_progress_review(week_doc, pq)
            raw_ix = pq.get("quiz_wrong_indices") or []
            wrong_snips: list[str] = []
            seen: set[int] = set()
            for x in raw_ix:
                try:
                    ix = int(x)
                except (TypeError, ValueError):
                    continue
                if ix in seen or ix < 0:
                    continue
                seen.add(ix)
                if session_items and 0 <= ix < len(session_items):
                    ttxt = str(session_items[ix].get("text") or "").strip()
                    sn = (ttxt[:140] + "…") if len(ttxt) > 140 else ttxt
                    wrong_snips.append(f"{ix + 1}번: {sn or '(지문 없음)'}")
            if wrong_snips:
                line += " | 오답: " + " · ".join(wrong_snips)
            elif qc < qt:
                line += " | 오답 문항은 저장되었으나 지문 미수록(수업 관리에서 문항 확인)"
            quiz_lines.append(line)
        quiz_block = "\n".join(quiz_lines) if quiz_lines else ""
        return weeks_lines, questions_block, quiz_block

    if not gemini_client.get_api_key():
        ui_messages.warn_gemini_key_missing()
    elif st.button(
        "학생 분석하기",
        type="primary",
        key=f"btn_stu_analyze_{category_id}_{student_uid}",
    ):
        try:
            weeks_lines, questions_block, quiz_block = _build_analysis_payload()
            with st.spinner("AI가 학습 패턴을 분석하는 중입니다…"):
                st.session_state[analysis_key] = gemini_client.analyze_student_learning_profile(
                    student_display_name=display_name,
                    course_name=course_name,
                    weeks_lines=weeks_lines,
                    questions_block=questions_block,
                    total_questions=total_q,
                    quiz_summary_block=quiz_block,
                    usage={
                        "org_id": org_id,
                        "category_id": category_id,
                        "bucket": "teacher_profile",
                        "usage_kind": "teacher_student_profile",
                    },
                )
        except Exception as e:
            err_s = str(e).lower()
            if "429" in err_s or "quota" in err_s or "resource exhausted" in err_s:
                st.error(gemini_client.format_quota_error_message(e))
            else:
                st.error(f"분석에 실패했습니다: {e}")

    if st.session_state.get(analysis_key):
        with st.expander("AI 학습 분석 결과 (펼치기/접기)", expanded=False):
            st.markdown(str(st.session_state[analysis_key]))


if not st.session_state.get(AUTH_UID):
    render_login_gate_with_intro(
        title="교사",
        description=(
            "사이드바 **교사 메뉴**에서 수업을 고른 뒤, 같은 메뉴의 **개요·학생 관리·수업 통계·수업 관리**로 "
            "화면을 바꿉니다.\n\n"
            "로그인 후 교사 권한이 있는 계정으로만 이용할 수 있습니다."
        ),
        login_button_key="login_gate_teacher",
    )

if st.session_state.get(AUTH_ROLE) != "Teacher":
    st.error("교사(Teacher) 계정만 이 메뉴를 사용할 수 있습니다.")
    st.stop()

uid = st.session_state[AUTH_UID]
org_id = (st.session_state.get(AUTH_ORG_ID) or "").strip()
cats: list[dict[str, Any]] = []
if org_id:
    cats = list_content_categories_for_teacher(org_id, uid)

render_teacher_sidebar(categories=cats if org_id else None)
render_sidebar_user_block(
    logout_key="sidebar_logout_teacher",
    management_org_name=st.session_state.get(AUTH_ORG_NAME) or None,
    show_top_divider=False,
)

st.title("교사")

cat_id = st.session_state.get(TEACHER_SELECTED_CATEGORY_ID)
sub_id = str(st.session_state.get(TEACHER_SELECTED_SUB_ITEM_ID) or "")

if not org_id:
    ui_messages.info_org_missing()
    st.stop()
if not cats:
    ui_messages.info_teacher_no_category()
    st.stop()

if not cat_id or not any(str(c.get("_doc_id")) == str(cat_id) for c in cats):
    ui_messages.info_teacher_select_course()
    st.stop()

cur = next((c for c in cats if str(c.get("_doc_id")) == str(cat_id)), None)
name = str((cur or {}).get("name") or "") if cur else ""

sub_list = get_teacher_category_sub_items(cur) if cur else []
sub_line = ""
for s in sub_list:
    if str(s.get("id")) == sub_id:
        sub_line = f"{s.get('icon', '')} {s.get('label', '')}".strip()
        break
if not sub_line and sub_list:
    sub_line = f"{sub_list[0].get('icon', '')} {sub_list[0].get('label', '')}".strip()

_fp = f"{cat_id}:{sub_id}"
if TEACHER_LESSON_FINGERPRINT in st.session_state and st.session_state[
    TEACHER_LESSON_FINGERPRINT
] != _fp:
    st.session_state[TEACHER_VIEW_TAB] = "overview"
    st.session_state.pop(TEACHER_STUDENT_DETAIL_UID, None)
st.session_state[TEACHER_LESSON_FINGERPRINT] = _fp

st.session_state.setdefault(TEACHER_VIEW_TAB, "overview")
tab = str(st.session_state.get(TEACHER_VIEW_TAB) or "overview")
if tab not in ("overview", "students", "course_stats", "ai_usage", "lesson_mgmt"):
    tab = "overview"
    st.session_state[TEACHER_VIEW_TAB] = tab

st.subheader(f"선택 수업 · {name or '(이름 없음)'}")
if sub_line:
    st.caption(f"{sub_line} · 카테고리 `{cat_id}`")
else:
    st.caption(f"카테고리 ID: `{cat_id}`")

st.divider()

if tab == "overview":
    cat_doc = get_content_category(org_id, str(cat_id)) or (cur or {})
    op_desc = str(cat_doc.get("description") or "").strip()
    teacher_ov = str(cat_doc.get("teacher_overview") or "")
    op_fb_teacher = str(cat_doc.get("operator_feedback_teacher") or "").strip()
    if op_fb_teacher:
        st.info(f"**운영자 피드백**\n\n{op_fb_teacher}")

    st.markdown("##### 수업 개요 (교사 작성)")
    st.caption(
        "학생 **수업 개요**에 표시됩니다. 운영자 설명과 별도로, 목표·대상·진행 방식·과제 안내 등을 적을 수 있습니다."
    )
    with st.form(f"form_teacher_overview_{cat_id}"):
        ta = st.text_area(
            "수업 개요",
            value=teacher_ov,
            height=180,
            placeholder="예: 이번 수업의 목표, 주차별 흐름, 과제·평가, 학습 시 유의사항",
        )
        if st.form_submit_button("수업 개요 저장", type="primary"):
            update_content_category(org_id, str(cat_id), teacher_overview=ta)
            st.success("저장했습니다.")
            st.rerun()

    st.markdown("##### 운영자 등록 설명")
    if op_desc:
        st.markdown(op_desc)
    else:
        st.caption("운영자가 입력한 수업 설명이 없습니다.")

    st.markdown("##### 주차 현황")
    st.caption(
        "왼쪽 **제목**을 누르면 **수업 관리** 탭으로 이동하며, 해당 주차 설정 화면이 열립니다."
    )
    ensure_lesson_weeks_seeded(org_id, str(cat_id), default_weeks=3)
    weeks = list_lesson_weeks(org_id, str(cat_id))
    if ensure_lesson_week_indices_contiguous(org_id, str(cat_id)):
        st.rerun()
    _pending_week = f"_lm_week_sel_pending_{cat_id}"
    if weeks:
        for w in weeks:
            wid = str(w.get("_doc_id") or "").strip()
            wi = int(w.get("week_index") or 0)
            wt = str(w.get("title") or f"{wi}주차").strip()
            vid = str(w.get("lesson_video_url") or "").strip()
            col_title, col_meta = st.columns([1.15, 2.1])
            with col_title:
                if st.button(
                    wt,
                    key=f"t_ov_open_week_{cat_id}_{wid}",
                    use_container_width=True,
                ):
                    st.session_state[TEACHER_VIEW_TAB] = "lesson_mgmt"
                    st.session_state[_pending_week] = wid
                    st.switch_page("pages/3_Teacher.py")
            with col_meta:
                st.markdown(f"**공개** · {week_access_label_short(w)}")
                st.caption(f"영상: **{'있음' if vid else '없음'}** · 주차 순번 {wi}")
            st.divider()
        st.caption(f"총 **{len(weeks)}**개 주차 · 세부 편집은 **수업 관리**에서 할 수 있습니다.")
    else:
        st.caption("등록된 주차가 없습니다. **수업 관리**에서 주차를 추가하세요.")

    st.markdown("##### 학생 AI 질문 (통계)")
    st.caption(
        "이 수업을 수강하는 학생이 **AI 채팅**에 남긴 질문·답변이 최신순으로 저장됩니다."
    )
    try:
        q_logs = list_student_lesson_questions_for_course(org_id, str(cat_id), limit=100)
    except Exception as e:
        q_logs = []
        st.caption(f"목록을 불러오지 못했습니다: {e}")
    if not q_logs:
        st.info("아직 저장된 학생 질문이 없습니다.")
    else:
        st.caption(f"최근 **{len(q_logs)}**건 표시")
        for row in q_logs:
            nm = (row.get("display_name") or "").strip() or "이름 없음"
            em = (row.get("student_email") or "").strip()
            wt = (row.get("week_title") or "").strip() or "—"
            wid = (row.get("week_doc_id") or "").strip()
            ts = _fmt_question_ts(row.get("created_at"))
            label = f"{ts} · {nm}"
            if em:
                label = f"{label} ({em})"
            with st.expander(label):
                vpos = (row.get("video_position_label") or "").strip()
                if not vpos and row.get("video_position_sec") is not None:
                    try:
                        s = float(row.get("video_position_sec"))
                        m = int(s // 60)
                        ss = int(round(s % 60))
                        vpos = f"{m}:{ss:02d}"
                    except (TypeError, ValueError):
                        vpos = ""
                cap = f"주차: **{wt}** · 문서 ID `{wid}`"
                if vpos:
                    cap += f" · 영상 위치 **{vpos}**"
                st.caption(cap)
                st.markdown("**질문**")
                st.write(row.get("question") or "")
                st.markdown("**답변**")
                st.write(row.get("answer") or "")

    st.info(
        "이 수업 맥락에서 **학생 관리**는 소속 학생 목록, **수업 관리**는 주차별 교안·자료·RAG 등을 "
        "설정합니다. 전환은 **왼쪽 교사 메뉴**에서 하세요."
    )

elif tab == "students":
    ensure_lesson_weeks_seeded(org_id, str(cat_id), default_weeks=3)
    weeks_for_stats = list_lesson_weeks(org_id, str(cat_id))
    if ensure_lesson_week_indices_contiguous(org_id, str(cat_id)):
        st.rerun()

    def _student_uid(u: dict) -> str:
        return str(u.get("uid") or u.get("_doc_id") or "")

    def _student_label(u: dict) -> str:
        nm = (u.get("display_name") or "").strip() or "이름 없음"
        em = str(u.get("email") or "")
        return f"{nm} · {em}"

    cat_doc = get_content_category(org_id, str(cat_id))
    raw_enrolled = (cat_doc or {}).get("student_uids") or []
    if not isinstance(raw_enrolled, list):
        raw_enrolled = []
    enrolled_ids = [str(x).strip() for x in raw_enrolled if str(x).strip()]

    users_all = list_users_by_org(org_id)
    by_uid = {_student_uid(u): u for u in users_all if _student_uid(u)}
    org_students = [u for u in users_all if str(u.get("role") or "") == "Student"]
    org_student_ids = {_student_uid(u) for u in org_students if _student_uid(u)}
    enrolled_ids = [u for u in enrolled_ids if u in org_student_ids]
    enrolled_ids = sorted(
        enrolled_ids,
        key=lambda i: _student_label(by_uid.get(i, {})),
    )

    _sel_detail = (st.session_state.get(TEACHER_STUDENT_DETAIL_UID) or "").strip()
    if _sel_detail and _sel_detail not in enrolled_ids:
        st.session_state.pop(TEACHER_STUDENT_DETAIL_UID, None)

    st.markdown("##### 이 수업 수강 학생")
    st.caption(
        f"**{name or '(이름 없음)'}**에 배정된 학생입니다. 같은 기업(학교) 소속 학생만 표시·추가됩니다."
    )
    if not org_students:
        st.warning(
            "이 기업에 등록된 학생 계정이 없습니다. 운영자에게 **관리 → 교사·학생**에서 초대를 요청하세요."
        )
    elif not enrolled_ids:
        st.info("아직 이 수업에 배정된 학생이 없습니다. 아래에서 추가할 수 있습니다.")
    else:
        for sid in enrolled_ids:
            u = by_uid.get(sid)
            nm = str((u or {}).get("display_name") or "(이름 없음)")
            em = str((u or {}).get("email") or "")
            c1, c2, c3 = st.columns([4, 1, 1])
            with c1:
                st.markdown(f"**{nm}** · `{em}`")
            with c2:
                if st.button(
                    "제외",
                    key=f"rm_stu_{cat_id}_{sid}",
                    type="secondary",
                ):
                    update_content_category(
                        org_id,
                        str(cat_id),
                        student_uids=[x for x in enrolled_ids if x != sid],
                    )
                    st.rerun()
            with c3:
                if st.button(
                    "정보 보기",
                    key=f"info_stu_{cat_id}_{sid}",
                    type="secondary",
                ):
                    st.session_state[TEACHER_STUDENT_DETAIL_UID] = sid
                    st.rerun()

    if enrolled_ids and (st.session_state.get(TEACHER_STUDENT_DETAIL_UID) or "").strip():
        sid = (st.session_state.get(TEACHER_STUDENT_DETAIL_UID) or "").strip()
        if sid in enrolled_ids:
            u = by_uid.get(sid)
            nm = str((u or {}).get("display_name") or "(이름 없음)")
            em = str((u or {}).get("email") or "")
            st.divider()
            with st.container(border=True):
                _render_student_info_panel(
                    org_id=org_id,
                    category_id=str(cat_id),
                    course_name=name or "(이름 없음)",
                    student_uid=sid,
                    weeks=weeks_for_stats,
                    display_name=nm,
                    email=em,
                )

    st.divider()
    st.markdown("##### 수업에 학생 추가")
    available = [
        u
        for u in org_students
        if _student_uid(u) and _student_uid(u) not in set(enrolled_ids)
    ]
    if not org_students:
        pass
    elif not available:
        st.caption("추가할 학생이 없습니다. (소속 학생이 모두 이미 배정되었거나, 남은 학생이 없습니다.)")
    else:
        labels = {_student_uid(u): _student_label(u) for u in available}
        ordered_uids = sorted(labels.keys(), key=lambda x: labels[x])
        with st.form(f"form_add_lesson_students_{cat_id}"):
            pick = st.multiselect(
                "같은 기업 소속 학생 중에서 선택",
                options=ordered_uids,
                format_func=lambda x: labels.get(x, x),
            )
            if st.form_submit_button("선택한 학생을 이 수업에 추가", type="primary"):
                if not pick:
                    st.warning("학생을 한 명 이상 선택하세요.")
                else:
                    merged = list(dict.fromkeys(enrolled_ids + list(pick)))
                    merged = [x for x in merged if x in org_student_ids]
                    update_content_category(
                        org_id,
                        str(cat_id),
                        student_uids=merged,
                    )
                    st.rerun()

    st.caption("배정은 현재 선택한 수업(콘텐츠 카테고리)에만 적용됩니다.")

elif tab == "course_stats":
    ensure_lesson_weeks_seeded(org_id, str(cat_id), default_weeks=3)
    if ensure_lesson_week_indices_contiguous(org_id, str(cat_id)):
        st.rerun()
    render_course_statistics_panel(
        org_id=org_id,
        category_id=str(cat_id),
        course_name=name or "(이름 없음)",
    )

elif tab == "ai_usage":
    ensure_lesson_weeks_seeded(org_id, str(cat_id), default_weeks=3)
    if ensure_lesson_week_indices_contiguous(org_id, str(cat_id)):
        st.rerun()
    render_teacher_ai_usage_panel(
        org_id=org_id,
        category_id=str(cat_id),
        course_name=name or "(이름 없음)",
    )

elif tab == "lesson_mgmt":
    org = get_organization(org_id)
    plan_label = normalize_plan(str((org or {}).get("plan") or "Starter"))
    st.markdown("##### 이 수업 맥락 · 수업 관리")
    st.caption(
        "단순 파일함이 아니라 **수업 설계도(Curriculum)** 를 AI와 함께 완성하는 컨트롤 타워입니다. "
        "주차별 **맥락 격리**로 AI 답변 정확도를 높입니다."
    )
    render_lesson_management_panel(
        org_id=org_id,
        category_id=str(cat_id),
        course_name=name or "(이름 없음)",
        plan_label=plan_label,
        sub_item_id=sub_id,
    )

else:
    st.session_state[TEACHER_VIEW_TAB] = "overview"
    st.rerun()
