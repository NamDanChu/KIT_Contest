"""교사·운영자 — 과목 통계(수강 인원·주차·질문·퀴즈 예정·AI 분석) 및 운영자 피드백."""

from __future__ import annotations

from collections import Counter
from typing import Any

import streamlit as st

from services import gemini_client
from services.firestore_repo import (
    aggregate_quiz_stats_for_course,
    get_content_category,
    get_student_lesson_progress_percent,
    list_lesson_weeks,
    list_student_lesson_questions_for_course,
    list_users_by_org,
    update_content_category,
)


def _student_uid(u: dict) -> str:
    return str(u.get("uid") or u.get("_doc_id") or "")


def _enrolled_student_ids(org_id: str, category_id: str) -> list[str]:
    cat_doc = get_content_category(org_id, category_id) or {}
    raw = (cat_doc or {}).get("student_uids") or []
    if not isinstance(raw, list):
        raw = []
    enrolled = [str(x).strip() for x in raw if str(x).strip()]
    users_all = list_users_by_org(org_id)
    org_students = [u for u in users_all if str(u.get("role") or "") == "Student"]
    org_ids = {_student_uid(u) for u in org_students if _student_uid(u)}
    enrolled = [u for u in enrolled if u in org_ids]
    return sorted(enrolled)


def _build_operator_feedback_ai_context(org_id: str, category_id: str) -> dict[str, Any]:
    """교사 피드백 AI 초안용 집계 문자열."""
    enrolled = _enrolled_student_ids(org_id, category_id)
    n = len(enrolled)
    weeks = list_lesson_weeks(org_id, category_id)
    q_rows = list_student_lesson_questions_for_course(org_id, category_id, limit=200)
    week_lines: list[str] = []
    for w in weeks:
        wid = str(w.get("_doc_id") or "")
        wi = int(w.get("week_index") or 0)
        wt = str(w.get("title") or f"{wi}주차")
        preview = str(w.get("ai_summary_preview") or "").strip()
        done = 0
        for uid in enrolled:
            if get_student_lesson_progress_percent(uid, org_id, category_id, wid) >= 100:
                done += 1
        week_lines.append(
            f"- {wt}: 100% 완료 {done}/{n}명. "
            + (preview[:180] + ("…" if len(preview) > 180 else "") if preview else "(요약 없음)")
        )
    weeks_block = "\n".join(week_lines) if week_lines else "(주차 없음)"
    q_digest_parts: list[str] = []
    for r in q_rows[:45]:
        nm = (r.get("display_name") or "").strip() or "—"
        wti = (r.get("week_title") or "").strip() or "—"
        qv = (r.get("question") or "").strip() or "—"
        vlab = (r.get("video_position_label") or "").strip()
        vextra = f" [영상 {vlab}]" if vlab else ""
        q_digest_parts.append(f"- {nm} · {wti}{vextra}: {qv[:220]}")
    questions_digest = (
        "\n".join(q_digest_parts) if q_digest_parts else "(질문 기록 없음)"
    )
    return {
        "n": n,
        "weeks_block": weeks_block,
        "questions_digest": questions_digest,
    }


def _render_operator_feedback_form(
    *, org_id: str, category_id: str, course_name: str
) -> None:
    """운영자 → 교사·학생 메모 저장 (카테고리 문서)."""
    cat = get_content_category(org_id, category_id) or {}
    fb_t = str(cat.get("operator_feedback_teacher") or "").strip()
    fb_s = str(cat.get("operator_feedback_student") or "").strip()
    kt = f"op_fb_teacher_{org_id}_{category_id}"
    ks = f"op_fb_student_{org_id}_{category_id}"
    if kt not in st.session_state:
        st.session_state[kt] = fb_t
    if ks not in st.session_state:
        st.session_state[ks] = fb_s

    st.divider()
    st.markdown("##### 운영자 피드백")
    st.caption(
        "아래 내용은 **저장 시** Firestore에 반영됩니다. "
        "**교사**에게는 교사 화면(개요 등)에서, **학생**에게는 수업 개요 화면에서 각각 확인할 수 있습니다."
    )
    c_ai, c_hint = st.columns([1, 2])
    with c_ai:
        if st.button(
            "AI로 교사 피드백 초안 작성",
            key=f"op_fb_ai_teacher_{org_id}_{category_id}",
            type="secondary",
            help="위 과목 통계·질문 요약을 바탕으로 Gemini가 초안을 채웁니다. 이후 자유롭게 수정하세요.",
        ):
            if not gemini_client.get_api_key():
                st.warning(
                    "`.streamlit/secrets.toml`에 `GEMINI_API_KEY`가 있어야 AI 초안을 쓸 수 있습니다."
                )
            else:
                try:
                    ctx = _build_operator_feedback_ai_context(org_id, category_id)
                    with st.spinner("AI가 교사 피드백 초안을 작성하는 중입니다…"):
                        draft = gemini_client.draft_operator_feedback_to_teacher(
                            course_name=course_name,
                            n_students=int(ctx["n"]),
                            weeks_summary_block=str(ctx["weeks_block"]),
                            questions_digest=str(ctx["questions_digest"]),
                        )
                    st.session_state[kt] = draft.strip()
                    st.rerun()
                except Exception as e:
                    err_s = str(e).lower()
                    if "429" in err_s or "quota" in err_s or "resource exhausted" in err_s:
                        st.error(gemini_client.format_quota_error_message(e))
                    else:
                        st.error(f"초안 작성에 실패했습니다: {e}")
    with c_hint:
        st.caption(
            "초안은 **교사 피드백** 칸에 들어갑니다. 마음에 들지 않으면 다시 눌러 덮어쓰거나 직접 수정한 뒤 저장하세요."
        )

    with st.form(f"op_feedback_save_{org_id}_{category_id}"):
        st.text_area(
            "교사에게 전달할 피드백",
            height=220,
            placeholder="수업 운영·교안·진행에 대한 운영자 코멘트(교사만 열람). 위 버튼으로 AI 초안을 넣은 뒤 수정해 저장하세요.",
            key=kt,
        )
        st.text_area(
            "학생에게 공개할 안내 (선택)",
            height=120,
            placeholder="학생 수업 개요에 표시할 공지·안내(선택)",
            key=ks,
        )
        if st.form_submit_button("피드백 저장", type="primary"):
            try:
                ta_t = str(st.session_state.get(kt) or "")
                ta_s = str(st.session_state.get(ks) or "")
                update_content_category(
                    org_id,
                    category_id,
                    operator_feedback_teacher=ta_t,
                    operator_feedback_student=ta_s,
                )
                st.session_state.pop(kt, None)
                st.session_state.pop(ks, None)
                st.success("저장했습니다.")
                st.rerun()
            except Exception as e:
                st.error(str(e))


def render_course_statistics_panel(
    *,
    org_id: str,
    category_id: str,
    course_name: str,
    operator_mode: bool = False,
) -> None:
    """교사 **수업 통계**와 동일한 집계. ``operator_mode=True`` 이면 하단에 운영자 피드백 폼이 붙습니다."""
    pfx = f"op_{org_id}_" if operator_mode else ""

    if operator_mode:
        st.markdown("##### 과목 통계")
        st.caption(
            f"교사 화면의 **수업 통계**와 동일한 형식입니다. **{course_name}** · 수강·주차·질문·AI 분석."
        )
    else:
        st.markdown("##### 수업 개요")
        st.caption(
            f"선택한 수업 **{course_name}** 의 수강 인원, 주차별 시청 완료, 질문·퀴즈(예정) 요약과 AI 분석입니다."
        )

    enrolled = _enrolled_student_ids(org_id, category_id)
    n = len(enrolled)
    st.metric("이 수업 수강(배정) 학생 수", f"{n}명")

    weeks = list_lesson_weeks(org_id, category_id)
    q_rows = list_student_lesson_questions_for_course(org_id, category_id, limit=200)
    cnt_by_week = Counter(str(r.get("week_doc_id") or "") for r in q_rows)
    quiz_agg = aggregate_quiz_stats_for_course(org_id, category_id, enrolled, weeks)
    quiz_by_week: dict[str, dict[str, Any]] = quiz_agg.get("by_week") or {}

    week_lines: list[str] = []
    week_stats: list[dict] = []

    if not weeks:
        st.info(
            "등록된 주차가 없습니다. 교사 **수업 관리**에서 주차를 추가하면 주차별 통계가 표시됩니다."
        )
    else:
        st.markdown("##### 주차별 현황")
        st.caption(
            "카드를 눌러 해당 주차의 **설명·질문 수**를 아래에서 확인하세요. "
            "(시청 완료는 **진행률 100%** 기준, 영상·Firebase 연동 시)"
        )

        for w in weeks:
            wid = str(w.get("_doc_id") or "")
            wi = int(w.get("week_index") or 0)
            wt = str(w.get("title") or f"{wi}주차")
            goals = str(w.get("learning_goals") or "").strip()
            preview = str(w.get("ai_summary_preview") or "").strip()
            done = 0
            for uid in enrolled:
                if get_student_lesson_progress_percent(uid, org_id, category_id, wid) >= 100:
                    done += 1
            week_lines.append(
                f"- {wt}: 100% 완료 {done}/{n}명. "
                + ("요약: " + preview[:200] if preview else "(요약 없음)")
            )
            week_stats.append(
                {
                    "wid": wid,
                    "wi": wi,
                    "title": wt,
                    "done": done,
                    "goals": goals,
                    "preview": preview,
                    "q_count": int(cnt_by_week.get(wid, 0)),
                }
            )

        sel_key = f"{pfx}course_stats_sel_week_{category_id}"
        if sel_key not in st.session_state:
            st.session_state[sel_key] = 0
        idx = int(st.session_state[sel_key])
        if idx >= len(weeks):
            idx = 0
            st.session_state[sel_key] = 0

        CHUNK = 6
        with st.container(border=True):
            for row_start in range(0, len(week_stats), CHUNK):
                chunk = week_stats[row_start : row_start + CHUNK]
                cols = st.columns(len(chunk))
                for j, stat in enumerate(chunk):
                    i = row_start + j
                    with cols[j]:
                        label = f"▶ {stat['wi']} 주\n✓ {stat['done']}/{n}"
                        if st.button(
                            label,
                            key=f"{pfx}cs_wk_{category_id}_{i}",
                            use_container_width=True,
                            type="primary" if idx == i else "secondary",
                        ):
                            st.session_state[sel_key] = i
                            st.rerun()

        sel = week_stats[idx]
        st.markdown("##### 선택한 주차 상세")
        with st.container(border=True):
            st.markdown(f"**{sel['title']}** · 시청 100% 완료 **{sel['done']}** / **{n}**명")
            st.caption(f"이 주차 AI 질문 **{sel['q_count']}**건")
            bw_sel = quiz_by_week.get(sel["wid"]) or {}
            n_sub_w = int(bw_sel.get("submissions") or 0)
            if n_sub_w > 0:
                att_w = int(bw_sel.get("attempts") or 0)
                wrong_w = int(bw_sel.get("wrong_sum") or 0)
                st.caption(
                    f"퀴즈(이 주차): 응시 **{att_w}**회(재시도 포함 합) · "
                    f"제출 기록 **{n_sub_w}**건(학생×주차) · 오답 문항 수 합 **{wrong_w}**개"
                )
                wc = bw_sel.get("wrong_idx_counts") or Counter()
                if isinstance(wc, Counter) and wc:
                    top_parts = [f"{i + 1}번×{c}회" for i, c in wc.most_common(5)]
                    st.caption(
                        "문항별 오답 빈도(학생 기준, 마지막 제출): " + " · ".join(top_parts)
                    )
            if sel["goals"]:
                st.markdown("**학습 목표**")
                st.write(sel["goals"])
            else:
                st.caption("학습 목표가 아직 없습니다. **수업 관리**에서 입력할 수 있습니다.")
            if sel["preview"]:
                st.markdown("**AI 요약·핵심(일부)**")
                st.write(sel["preview"])
            else:
                st.caption("AI 요약이 아직 없습니다. 수업 관리에서 자료·요약을 반영할 수 있습니다.")

    st.markdown("##### 질문·참여 요약")
    st.caption(f"저장된 **학생 AI 질문** 최근 기준 **{len(q_rows)}**건(상한 200)이 이 수업에 있습니다.")

    st.markdown("##### 퀴즈·평가")
    ta = int(quiz_agg.get("total_attempts") or 0)
    ns = int(quiz_agg.get("n_submissions") or 0)
    tw = int(quiz_agg.get("total_wrong") or 0)
    if ns <= 0:
        st.caption(
            "아직 이 수업에 **퀴즈 제출 기록**이 없습니다. 학생이 퀴즈를 제출하면 "
            "응시 횟수·오답 수가 집계됩니다."
        )
    else:
        q1, q2, q3 = st.columns(3)
        with q1:
            st.metric("퀴즈 응시(제출) 횟수 합계", f"{ta}회")
        with q2:
            st.metric("제출 기록(학생×주차)", f"{ns}건")
        with q3:
            st.metric("오답 문항 수 합계", f"{tw}개")
        st.caption(
            "응시 횟수는 **재시도 포함** 제출 횟수의 합입니다. 오답 수는 **마지막 제출** 기준 "
            "(문항 수 − 정답 수)를 학생·주차별로 합산한 값입니다."
        )

    qb_lines: list[str] = [
        f"퀴즈 집계: 총 응시(제출) 횟수 합 {ta}회, 제출 기록 {ns}건(학생×주차), 오답 문항 수 합계 {tw}개."
    ]
    for w in weeks:
        wid = str(w.get("_doc_id") or "")
        bw = quiz_by_week.get(wid) or {}
        nsw = int(bw.get("submissions") or 0)
        if nsw <= 0:
            continue
        wt = str(w.get("title") or "").strip() or wid
        wc = bw.get("wrong_idx_counts") or Counter()
        top_s = ""
        if isinstance(wc, Counter) and wc:
            top_s = ", ".join(f"{i + 1}번×{c}" for i, c in wc.most_common(4))
        qb_lines.append(
            f"- {wt}: 응시 {int(bw.get('attempts') or 0)}회, 제출 {nsw}건, 오답합 {int(bw.get('wrong_sum') or 0)}개"
            + (f", 다빈도 문항 {top_s}" if top_s else "")
        )
    quiz_block = "\n".join(qb_lines) if qb_lines else "(퀴즈 제출 기록 없음)"

    st.divider()
    st.markdown("##### 수업 전반 AI 분석")
    cache_key = f"teacher_course_analysis_md_{category_id}"
    if not gemini_client.get_api_key():
        st.warning(
            "Gemini API 키가 없습니다. `.streamlit/secrets.toml`에 `GEMINI_API_KEY`를 설정하면 "
            "분석을 사용할 수 있습니다."
        )
    elif st.button(
        "수업 통계 분석하기",
        type="primary",
        key=f"{pfx}btn_course_analyze_{category_id}",
    ):
        try:
            weeks_summary_block = "\n".join(week_lines) if week_lines else "(주차 없음)"
            q_digest_parts: list[str] = []
            for r in q_rows[:80]:
                nm = (r.get("display_name") or "").strip() or "—"
                wti = (r.get("week_title") or "").strip() or "—"
                qv = (r.get("question") or "").strip() or "—"
                vlab = (r.get("video_position_label") or "").strip()
                vextra = f" [영상 {vlab}]" if vlab else ""
                q_digest_parts.append(f"- {nm} · {wti}{vextra}: {qv[:300]}")
            questions_digest = (
                "\n".join(q_digest_parts) if q_digest_parts else "(질문 기록 없음)"
            )
            with st.spinner("AI가 수업 데이터를 분석하는 중입니다…"):
                st.session_state[cache_key] = gemini_client.analyze_course_statistics(
                    course_name=course_name,
                    n_students=n,
                    weeks_summary_block=weeks_summary_block,
                    quiz_block=quiz_block,
                    questions_digest=questions_digest,
                )
        except Exception as e:
            err_s = str(e).lower()
            if "429" in err_s or "quota" in err_s or "resource exhausted" in err_s:
                st.error(gemini_client.format_quota_error_message(e))
            else:
                st.error(f"분석에 실패했습니다: {e}")

    if st.session_state.get(cache_key):
        with st.expander("AI 분석 결과 (펼치기/접기)", expanded=False):
            st.markdown(str(st.session_state[cache_key]))

    if operator_mode:
        _render_operator_feedback_form(
            org_id=org_id, category_id=category_id, course_name=course_name
        )
