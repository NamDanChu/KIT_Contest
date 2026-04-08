"""학생 — 통합 퀴즈: 여러 회차 문항을 합쳐 연습 + Gemini 해설·보완점."""

from __future__ import annotations

import html
import random
import time
from typing import Any

import streamlit as st

from services import gemini_client
from services import ui_messages
from services.session_keys import STUDENT_QUIZ_MIX_PHASE
from services.firestore_repo import (
    append_student_integrated_quiz_log,
    get_lesson_week,
    list_lesson_weeks,
)
from services.lesson_access import week_in_student_list
from services.quiz_items import quiz_pool_for_week
from services.student_portal import _inject_quiz_exam_css


def _marks() -> tuple[str, ...]:
    return ("①", "②", "③", "④")


# 객관식 미선택 (Streamlit radio 첫 보기가 자동 선택되지 않도록 구분)
UNSET_ANSWER = -1


def _init_mix_answer_keys(cid: str, n_q: int) -> None:
    for j in range(n_q):
        k = f"stu_mix_q_{cid}_{j}"
        if k not in st.session_state:
            st.session_state[k] = UNSET_ANSWER


def _int_answer(raw: Any) -> int:
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return UNSET_ANSWER
    return v if v >= 0 else UNSET_ANSWER


def _unanswered_question_nums(cid: str, n_q: int) -> list[int]:
    out: list[int] = []
    for j in range(n_q):
        if _int_answer(st.session_state.get(f"stu_mix_q_{cid}_{j}")) == UNSET_ANSWER:
            out.append(j + 1)
    return out


def _label_for_sel(marks: tuple[str, ...], raw: Any) -> str:
    v = _int_answer(raw)
    if v == UNSET_ANSWER:
        return "미선택"
    return marks[v] if v < len(marks) else "—"


def _mix_star_idx_key(cid: str) -> str:
    return f"mix_star_idx_{cid}"


def _get_mix_star_index_list(cid: str) -> list[int]:
    """다시 볼 표시한 문항 인덱스(0-based). 위젯 키와 분리해 문항 이동 후에도 유지된다."""
    k = _mix_star_idx_key(cid)
    raw = st.session_state.get(k)
    if not isinstance(raw, list):
        st.session_state[k] = []
        return st.session_state[k]  # type: ignore[return-value]
    out: list[int] = []
    for x in raw:
        try:
            ix = int(x)
        except (TypeError, ValueError):
            continue
        if ix >= 0 and ix not in out:
            out.append(ix)
    st.session_state[k] = out
    return out


def _migrate_legacy_mix_star_widgets(cid: str, n_q: int, star_list: list[int]) -> None:
    """예전 문항별 체크박스 키(stu_mix_star_*)를 리스트로 옮긴 뒤 제거."""
    for j in range(n_q):
        lk = f"stu_mix_star_{cid}_{j}"
        if lk in st.session_state and bool(st.session_state.get(lk)):
            if j not in star_list:
                star_list.append(j)
        st.session_state.pop(lk, None)


def _stable_qid(item: dict[str, Any]) -> str:
    """문항 고유 id (주차 + 지문 앞부분 해시)."""
    wd = str(item.get("week_doc_id") or "")
    t = str(item.get("text") or "").strip()[:280]
    h = hash((wd, t)) & 0xFFFFFFFF
    return f"{wd}:{h:08x}"


def _weighted_pick_infinite(
    pool: list[dict[str, Any]],
    wrong_by_qid: dict[str, int],
    week_wrong: dict[str, int],
    *,
    alpha: float = 2.2,
    beta: float = 0.35,
) -> dict[str, Any]:
    """오답이 많은 문항·주차 가중치를 높여 다음 문항을 고른다."""
    if not pool:
        raise ValueError("pool empty")
    wts: list[float] = []
    for it in pool:
        qid = _stable_qid(it)
        wd = str(it.get("week_doc_id") or "")
        w = 1.0 + alpha * float(wrong_by_qid.get(qid, 0))
        w += beta * float(week_wrong.get(wd, 0))
        wts.append(max(0.2, w))
    ri = int(random.choices(range(len(pool)), weights=wts, k=1)[0])
    return dict(pool[ri])


def _clear_inf_keys(cid: str) -> None:
    for suffix in (
        "week_ids",
        "wrong",
        "attempt",
        "week_wrong",
        "cur",
        "sub",
        "sel",
        "total",
        "ai_md",
        "started",
        "last_ok",
        "last_pick",
    ):
        st.session_state.pop(f"mix_inf_{suffix}_{cid}", None)


def _format_inf_stats_for_gemini(
    wrong_by_qid: dict[str, int],
    attempt_by_qid: dict[str, int],
    week_wrong: dict[str, int],
    pool: list[dict[str, Any]],
) -> str:
    """Gemini용: 내부 문항 ID·문서 ID 없이 주차 제목·횟수만 전달."""
    qid_to_week_title: dict[str, str] = {}
    wid_to_title: dict[str, str] = {}
    for it in pool:
        wd = str(it.get("week_doc_id") or "")
        wt = str(it.get("week_title") or "기타").strip()[:80]
        if wd:
            wid_to_title[wd] = wt
        qid = _stable_qid(it)
        if qid not in qid_to_week_title:
            qid_to_week_title[qid] = wt
    wrong_by_title: dict[str, int] = {}
    attempt_by_title: dict[str, int] = {}
    for qid, w in wrong_by_qid.items():
        t = qid_to_week_title.get(qid, "기타")
        wrong_by_title[t] = wrong_by_title.get(t, 0) + int(w)
    for qid, a in attempt_by_qid.items():
        t = qid_to_week_title.get(qid, "기타")
        attempt_by_title[t] = attempt_by_title.get(t, 0) + int(a)
    lines: list[str] = []
    lines.append("[주차 범위별 — 지문 유형 기준 누적]")
    for t, w in sorted(wrong_by_title.items(), key=lambda x: -x[1])[:25]:
        att = attempt_by_title.get(t, 0)
        lines.append(f"- {t}: 오답 {w}회, 정답 확인(시도) 누적 {att}회")
    lines.append("")
    lines.append("[주차별 오답 누적 — 출제 가중치에 반영]")
    for wd, w in sorted(week_wrong.items(), key=lambda x: -x[1])[:20]:
        lab = wid_to_title.get(wd, "기타")
        lines.append(f"- {lab}: 오답 {w}회")
    return "\n".join(lines) if lines else "(아직 오답 기록 없음)"


def _try_append_integrated_quiz_log(
    *,
    org_id: str,
    category_id: str,
    course_name: str,
    student_uid: str,
    student_email: str,
    display_name: str,
    event_type: str,
    details: dict[str, Any],
) -> None:
    uid = (student_uid or "").strip()
    if not uid:
        return
    try:
        append_student_integrated_quiz_log(
            org_id,
            category_id,
            uid,
            course_name=course_name,
            event_type=event_type,
            details=details,
            student_email=student_email or None,
            display_name=display_name or None,
        )
    except Exception:
        pass


def _build_pool_for_weeks(
    org_id: str,
    category_id: str,
    week_doc_ids: list[str],
) -> list[dict[str, Any]]:
    pool: list[dict[str, Any]] = []
    for wid in week_doc_ids:
        wid = str(wid).strip()
        if not wid:
            continue
        w = get_lesson_week(org_id, category_id, wid)
        if not w or not week_in_student_list(w):
            continue
        if str(w.get("quiz_mode") or "off") == "off":
            continue
        items = quiz_pool_for_week(w)
        if not items:
            continue
        wi = int(w.get("week_index") or 0)
        wt = str(w.get("title") or f"{wi}주차")
        for it in items:
            row = dict(it)
            row["week_title"] = wt
            row["week_doc_id"] = wid
            pool.append(row)
    return pool


def _clear_mix_keys(category_id: str, n_radio: int) -> None:
    cid = str(category_id)
    for j in range(max(n_radio, 64)):
        st.session_state.pop(f"stu_mix_q_{cid}_{j}", None)
        st.session_state.pop(f"stu_mix_star_{cid}_{j}", None)
    st.session_state.pop(f"mix_session_{cid}", None)
    st.session_state.pop(f"mix_review_{cid}", None)
    st.session_state.pop(f"mix_started_{cid}", None)
    st.session_state.pop(f"stu_mix_idx_{cid}", None)
    st.session_state.pop(_mix_star_idx_key(cid), None)
    st.session_state.pop(f"mix_star_chk_{cid}", None)
    st.session_state.pop(f"mix_star_last_ti_{cid}", None)
    _clear_inf_keys(cid)
    st.session_state.pop(f"mix_style_{cid}", None)
    st.session_state.pop(f"mix_fs_batch_logged_{cid}", None)


def clear_quiz_mix_state_for_nav(category_id: str | None) -> None:
    """개요·수업 화면으로 나갈 때 통합 퀴즈 세션·답안 키를 정리한다."""
    st.session_state.pop(STUDENT_QUIZ_MIX_PHASE, None)
    if not category_id:
        return
    cid = str(category_id)
    for j in range(64):
        st.session_state.pop(f"stu_mix_q_{cid}_{j}", None)
        st.session_state.pop(f"stu_mix_star_{cid}_{j}", None)
    st.session_state.pop(f"mix_session_{cid}", None)
    st.session_state.pop(f"mix_review_{cid}", None)
    st.session_state.pop(f"mix_started_{cid}", None)
    st.session_state.pop(f"stu_mix_idx_{cid}", None)
    st.session_state.pop(_mix_star_idx_key(cid), None)
    st.session_state.pop(f"mix_star_chk_{cid}", None)
    st.session_state.pop(f"mix_star_last_ti_{cid}", None)
    _clear_inf_keys(cid)
    st.session_state.pop(f"mix_style_{cid}", None)
    st.session_state.pop(f"mix_fs_batch_logged_{cid}", None)


def _render_infinite_quiz_mode(
    *,
    org_id: str,
    category_id: str,
    course_name: str,
    cid: str,
    student_uid: str = "",
    student_email: str = "",
    display_name: str = "",
) -> None:
    marks = _marks()
    _inject_quiz_exam_css()

    pool_ids = list(st.session_state.get(f"mix_inf_week_ids_{cid}") or [])
    pool = _build_pool_for_weeks(org_id, category_id, pool_ids) if pool_ids else []
    if not pool:
        st.warning("문항이 없거나 세션이 만료되었습니다. 처음 화면으로 돌아갑니다.")
        _clear_inf_keys(cid)
        st.session_state[STUDENT_QUIZ_MIX_PHASE] = "setup"
        st.rerun()
        return

    wid_to_title: dict[str, str] = {}
    for _it in pool:
        _wd = str(_it.get("week_doc_id") or "")
        if _wd and _wd not in wid_to_title:
            wid_to_title[_wd] = str(_it.get("week_title") or "").strip() or "주차"

    wrong_by_qid: Any = st.session_state.get(f"mix_inf_wrong_{cid}") or {}
    attempt_by_qid: Any = st.session_state.get(f"mix_inf_attempt_{cid}") or {}
    week_wrong: Any = st.session_state.get(f"mix_inf_week_wrong_{cid}") or {}
    if not isinstance(wrong_by_qid, dict):
        wrong_by_qid = {}
    if not isinstance(attempt_by_qid, dict):
        attempt_by_qid = {}
    if not isinstance(week_wrong, dict):
        week_wrong = {}
    wb: dict[str, int] = {str(k): int(v) for k, v in wrong_by_qid.items()}
    ab: dict[str, int] = {str(k): int(v) for k, v in attempt_by_qid.items()}
    ww: dict[str, int] = {str(k): int(v) for k, v in week_wrong.items()}

    tkey = f"mix_inf_started_{cid}"
    if tkey not in st.session_state:
        st.session_state[tkey] = time.time()
    elapsed = int(time.time() - float(st.session_state.get(tkey) or time.time()))
    em, es = elapsed // 60, elapsed % 60
    total_a = int(st.session_state.get(f"mix_inf_total_{cid}") or 0)

    sub = str(st.session_state.get(f"mix_inf_sub_{cid}") or "answer")
    cur: dict[str, Any] | None = st.session_state.get(f"mix_inf_cur_{cid}")
    if cur is None:
        cur = _weighted_pick_infinite(pool, wb, ww)
        st.session_state[f"mix_inf_cur_{cid}"] = cur
        st.session_state[f"mix_inf_sub_{cid}"] = "answer"

    n_show = total_a + 1
    st.markdown(
        f"##### 무한 연습 · 이번 세션 **{n_show}**번째 문제 · 경과 {em:02d}:{es:02d}"
    )
    st.caption(
        "보기를 고른 뒤 **정답 확인**을 누르면 바로 채점·해설이 나옵니다. "
        "틀린 문항·주차는 가중치가 올라가 비슷한 범위가 더 자주 출제됩니다."
    )

    main_i, side_i = st.columns([2.25, 1])
    with side_i:
        st.markdown("### 누적")
        st.caption(f"정답 확인까지 누적: **{total_a}**회")
        topw = sorted(ww.items(), key=lambda x: -x[1])[:8]
        if topw:
            st.caption("주차별 오답 누적 — 많을수록 출제 비중 ↑")
            for wd, cnt in topw:
                lab = wid_to_title.get(wd, "주차")
                short = lab if len(lab) <= 28 else lab[:26] + "…"
                st.caption(f"- **{short}** · {cnt}회")
        if st.button("AI 코칭 요약", key=f"mix_inf_ai_btn_{cid}", use_container_width=True):
            if not gemini_client.get_api_key():
                ui_messages.warn_gemini_key_missing()
            else:
                try:
                    stats_txt = _format_inf_stats_for_gemini(wb, ab, ww, pool)
                    with st.spinner("AI가 약점·복습 방향을 정리하는 중…"):
                        note = gemini_client.infinite_quiz_coach_note(
                            course_name=course_name,
                            stats_block=stats_txt,
                            usage={
                                "org_id": org_id,
                                "category_id": category_id,
                                "bucket": "student_quiz",
                                "usage_kind": "student_quiz_infinite_coach",
                            },
                        )
                    st.session_state[f"mix_inf_ai_md_{cid}"] = note
                except Exception as e:
                    st.session_state[f"mix_inf_ai_md_{cid}"] = ""
                    err_s = str(e).lower()
                    if "429" in err_s or "quota" in err_s or "resource exhausted" in err_s:
                        st.error(gemini_client.format_quota_error_message(e))
                    else:
                        st.error(f"AI 요약 생성에 실패했습니다: {e}")
                st.rerun()
        ai_note = str(st.session_state.get(f"mix_inf_ai_md_{cid}") or "").strip()
        if ai_note:
            with st.expander("AI 코칭 요약 (결과)", expanded=False):
                st.markdown(ai_note)
        else:
            st.caption("위 버튼을 누르면 현재 누적 통계로 코칭을 받을 수 있습니다.")

    with main_i:
        assert cur is not None
        cor = int(cur.get("correct") or 0)
        opts = list(cur.get("options") or [])
        wt = html.escape(str(cur.get("week_title") or ""))
        qbody = html.escape(str(cur.get("text") or ""))

        if sub == "answer":
            st.markdown(
                f'<div class="exam-paper"><span style="font-size:0.85rem;color:#666;">{wt}</span>'
                f'<div class="exam-qhead"><span class="exam-qno">∞</span>'
                f'<div style="flex:1;font-size:1.02rem;line-height:1.55;color:#1a1a1a;">{qbody}</div></div>',
                unsafe_allow_html=True,
            )
            st.markdown("##### 보기")
            for ki in range(min(4, len(opts))):
                st.markdown(
                    f'<p style="margin:0.15rem 0;font-size:0.95rem;">'
                    f"<b>{marks[ki]}</b> {html.escape(str(opts[ki]))}</p>",
                    unsafe_allow_html=True,
                )
            sel_k = f"mix_inf_sel_{cid}"
            if sel_k not in st.session_state:
                st.session_state[sel_k] = UNSET_ANSWER
            pick = _int_answer(st.session_state.get(sel_k))
            pc = st.columns(4)
            for k in range(4):
                with pc[k]:
                    if st.button(
                        marks[k],
                        key=f"mix_inf_ab_{cid}_{k}",
                        type="primary" if pick == k else "secondary",
                        use_container_width=True,
                        help=str(opts[k])[:220] if k < len(opts) else "",
                    ):
                        st.session_state[sel_k] = k
                        st.rerun()
            if st.button("정답 확인", key=f"mix_inf_check_{cid}", type="primary"):
                pick2 = _int_answer(st.session_state.get(sel_k))
                if pick2 == UNSET_ANSWER:
                    st.warning("①~④ 중 하나를 선택하세요.")
                else:
                    ok = pick2 == cor
                    qid = _stable_qid(cur)
                    ab[qid] = ab.get(qid, 0) + 1
                    if not ok:
                        wb[qid] = wb.get(qid, 0) + 1
                        wd = str(cur.get("week_doc_id") or "")
                        ww[wd] = ww.get(wd, 0) + 1
                    st.session_state[f"mix_inf_wrong_{cid}"] = wb
                    st.session_state[f"mix_inf_attempt_{cid}"] = ab
                    st.session_state[f"mix_inf_week_wrong_{cid}"] = ww
                    st.session_state[f"mix_inf_total_{cid}"] = total_a + 1
                    st.session_state[f"mix_inf_last_ok_{cid}"] = ok
                    st.session_state[f"mix_inf_last_pick_{cid}"] = pick2
                    st.session_state[f"mix_inf_sub_{cid}"] = "feedback"
                    _try_append_integrated_quiz_log(
                        org_id=org_id,
                        category_id=category_id,
                        course_name=course_name,
                        student_uid=student_uid,
                        student_email=student_email,
                        display_name=display_name,
                        event_type="infinite_answer",
                        details={
                            "mode": "infinite",
                            "week_title": str(cur.get("week_title") or ""),
                            "week_doc_id": str(cur.get("week_doc_id") or ""),
                            "question_preview": str(cur.get("text") or "")[:500],
                            "is_correct": ok,
                            "picked_index": pick2,
                            "correct_index": cor,
                            "check_index_in_session": total_a + 1,
                            "elapsed_sec": elapsed,
                        },
                    )
                    st.rerun()

        else:
            ok = bool(st.session_state.get(f"mix_inf_last_ok_{cid}"))
            pick = int(st.session_state.get(f"mix_inf_last_pick_{cid}") or 0)
            if ok:
                st.success("정답입니다.")
            else:
                st.error("오답입니다.")
            st.caption(
                f"내 선택: **{marks[pick] if 0 <= pick < 4 else '?'}**  "
                f"정답: **{marks[cor] if cor < 4 else '?'}**"
            )
            ex = str(cur.get("explanation") or "").strip()
            if ex:
                st.info(ex)
            else:
                st.caption("등록된 해설이 없습니다.")
            nb, bk = st.columns(2)
            with nb:
                if st.button("다음 문제", key=f"mix_inf_next_{cid}", type="primary"):
                    nxt = _weighted_pick_infinite(pool, wb, ww)
                    st.session_state[f"mix_inf_cur_{cid}"] = nxt
                    st.session_state[f"mix_inf_sub_{cid}"] = "answer"
                    st.session_state.pop(f"mix_inf_sel_{cid}", None)
                    st.rerun()
            with bk:
                if st.button("돌아가기", key=f"mix_inf_back_{cid}"):
                    wrong_by_week_title: dict[str, int] = {}
                    for _wd, _n in ww.items():
                        _lab = wid_to_title.get(_wd, "기타")
                        wrong_by_week_title[_lab] = wrong_by_week_title.get(_lab, 0) + int(
                            _n
                        )
                    _try_append_integrated_quiz_log(
                        org_id=org_id,
                        category_id=category_id,
                        course_name=course_name,
                        student_uid=student_uid,
                        student_email=student_email,
                        display_name=display_name,
                        event_type="infinite_session_end",
                        details={
                            "mode": "infinite",
                            "total_checks": int(
                                st.session_state.get(f"mix_inf_total_{cid}") or 0
                            ),
                            "elapsed_sec": elapsed,
                            "wrong_by_week_title": wrong_by_week_title,
                            "wrong_by_week_doc_id": dict(ww),
                            "ai_coaching_md": str(
                                st.session_state.get(f"mix_inf_ai_md_{cid}") or ""
                            )[:12000],
                        },
                    )
                    _clear_mix_keys(cid, 64)
                    st.session_state[STUDENT_QUIZ_MIX_PHASE] = "setup"
                    st.rerun()


def render_student_quiz_mix(
    *,
    org_id: str,
    category_id: str,
    course_name: str,
    student_uid: str = "",
    student_email: str = "",
    display_name: str = "",
) -> None:
    """통합 퀴즈 탭 본문."""
    cid = str(category_id)
    phase = str(st.session_state.get(STUDENT_QUIZ_MIX_PHASE) or "setup")
    if phase not in ("setup", "run", "done", "inf_run"):
        phase = "setup"
        st.session_state[STUDENT_QUIZ_MIX_PHASE] = phase

    sk_session = f"mix_session_{cid}"
    sk_review = f"mix_review_{cid}"

    st.title("통합 퀴즈")
    st.caption(
        f"**{course_name}** — 여러 회차를 섞어 **일괄 연습**하거나 **무한 연습**(한 문제씩 즉시 해설)할 수 있습니다. "
        "(정식 수업 퀴즈 제출 기록과는 별도입니다.)"
    )

    # --- 무한 연습 ---
    if phase == "inf_run":
        _render_infinite_quiz_mode(
            org_id=org_id,
            category_id=category_id,
            course_name=course_name,
            cid=cid,
            student_uid=student_uid,
            student_email=student_email,
            display_name=display_name,
        )
        return

    # --- 결과 ---
    if phase == "done":
        session: list[dict[str, Any]] = list(st.session_state.get(sk_session) or [])
        review = str(st.session_state.get(sk_review) or "").strip()
        answers = [
            _int_answer(st.session_state.get(f"stu_mix_q_{cid}_{j}"))
            for j in range(len(session))
        ]
        correct_n = sum(
            1
            for j, it in enumerate(session)
            if answers[j] == int(it.get("correct") or 0)
        )
        tq = len(session)
        marks = _marks()
        st.success(f"채점 결과: **{correct_n}** / **{tq}** 문항 정답")
        if review:
            st.markdown("##### AI 총평·해설·보완점")
            st.markdown(review)
        else:
            st.caption("(AI 해설을 불러오지 못했습니다. 아래 문항별 해설을 확인하세요.)")

        st.markdown("##### 문항별 확인")
        for j, it in enumerate(session):
            opts = list(it.get("options") or [])
            cor = int(it.get("correct") or 0)
            ok = answers[j] == cor
            wt = str(it.get("week_title") or "")
            badge = "정답" if ok else "오답"
            st.markdown(f"**{j + 1}.** [{wt}] · {badge}")
            st.write(str(it.get("text") or ""))
            my_l = (
                marks[answers[j]]
                if 0 <= answers[j] < 4
                else ("미선택" if answers[j] == UNSET_ANSWER else "—")
            )
            st.caption(
                f"내 선택: {my_l}  "
                f"정답: {marks[cor] if cor < len(marks) else '—'}"
            )
            ex = str(it.get("explanation") or "").strip()
            if ex:
                with st.expander(f"등록된 해설 · {j + 1}번", expanded=not ok):
                    st.info(ex)
            st.divider()

        if st.button("돌아가기", key=f"mix_back_setup_{cid}", type="primary"):
            _clear_mix_keys(cid, len(session))
            st.session_state[STUDENT_QUIZ_MIX_PHASE] = "setup"
            st.rerun()
        return

    # --- 풀이 중 ---
    if phase == "run":
        session = list(st.session_state.get(sk_session) or [])
        if not session:
            st.warning("세션이 없습니다. 설정부터 다시 시작하세요.")
            st.session_state[STUDENT_QUIZ_MIX_PHASE] = "setup"
            st.rerun()
            return

        _inject_quiz_exam_css()
        tkey = f"mix_started_{cid}"
        if tkey not in st.session_state:
            st.session_state[tkey] = time.time()
        elapsed = int(time.time() - float(st.session_state.get(tkey) or time.time()))
        em, es = elapsed // 60, elapsed % 60

        marks = _marks()
        st.markdown(
            f"##### 연습 퀴즈 · {len(session)}문항 · 경과 {em:02d}:{es:02d}"
        )
        st.caption(
            "**이전·다음** 또는 오른쪽 **전체 답안**에서 문항을 눌러 이동하세요. "
            "보기는 **①~④ 버튼**으로만 고릅니다. "
            "**채점·해설 보기**에서 전부 고른 뒤 채점됩니다."
        )

        n_q = len(session)
        idx_key = f"stu_mix_idx_{cid}"
        if idx_key not in st.session_state:
            st.session_state[idx_key] = 0
        ti = max(0, min(n_q - 1, int(st.session_state.get(idx_key) or 0)))
        st.session_state[idx_key] = ti

        _init_mix_answer_keys(cid, n_q)
        star_list = _get_mix_star_index_list(cid)
        _migrate_legacy_mix_star_widgets(cid, n_q, star_list)

        n_answered = sum(
            1
            for j in range(n_q)
            if _int_answer(st.session_state.get(f"stu_mix_q_{cid}_{j}")) != UNSET_ANSWER
        )

        # 문항이 많을 때 우측 전체 목록이 과도하게 길어지지 않도록: 요약은 항상 짧게,
        # 전체 목록은 접었다 펼치기 + 스크롤.
        main_c, nav_c = st.columns([3.25, 0.92])
        with nav_c:
            st.markdown(
                "<style>"
                "[data-testid='stSidebar'] section[data-testid='stExpander'] "
                "div[data-testid='stExpanderDetails'] {"
                "max-height: min(380px, 48vh);"
                "overflow-y: auto;"
                "overflow-x: hidden;"
                "padding-right: 0.35rem;"
                "}"
                "</style>",
                unsafe_allow_html=True,
            )
            st.markdown("### 진행")
            cur_raw = st.session_state.get(f"stu_mix_q_{cid}_{ti}")
            cur_l = _label_for_sel(marks, cur_raw)
            wt_now = html.escape(str(session[ti].get("week_title") or "")[:16])
            st.caption(f"**이번 문항** ({ti + 1}/{n_q})")
            st.caption(f"{wt_now}")
            st.markdown(f"선택 **{cur_l}**")
            st.caption(f"응답 **{n_answered}** / {n_q}문항")
            try:
                st.progress(min(1.0, max(0.0, (ti + 1) / float(n_q))))
            except Exception:
                pass
            exp_label = f"전체 답안 ({n_q}문항)"
            with st.expander(exp_label, expanded=n_q <= 12):
                st.caption("항목을 누르면 해당 문항으로 이동합니다.")
                nps = 2
                for r in range((n_q + nps - 1) // nps):
                    cols_s = st.columns(nps)
                    for c in range(nps):
                        j = r * nps + c
                        if j >= n_q:
                            break
                        with cols_s[c]:
                            sel_raw = st.session_state.get(f"stu_mix_q_{cid}_{j}")
                            sel_l = _label_for_sel(marks, sel_raw)
                            star_on = j in star_list
                            wj = str(session[j].get("week_title") or "")[:10]
                            prefix = "⭐ " if star_on else ""
                            btn_lbl = f"{prefix}{j + 1}. [{wj}] · {sel_l}"
                            if len(btn_lbl) > 44:
                                btn_lbl = btn_lbl[:42] + "…"
                            if st.button(
                                btn_lbl,
                                key=f"mix_side_{cid}_{j}",
                                type="primary" if j == ti else "secondary",
                                use_container_width=True,
                            ):
                                st.session_state[idx_key] = j
                                st.rerun()

        with main_c:
            it = session[ti]
            opts = list(it.get("options") or [])
            wt = html.escape(str(it.get("week_title") or ""))
            qbody = html.escape(str(it.get("text") or ""))
            st.markdown(
                f'<div class="exam-paper"><span style="font-size:0.85rem;color:#666;">{wt}</span>'
                f'<div class="exam-qhead"><span class="exam-qno">{ti + 1}</span>'
                f'<div style="flex:1;font-size:1.02rem;line-height:1.55;color:#1a1a1a;">{qbody}</div></div>',
                unsafe_allow_html=True,
            )
            chk_star = f"mix_star_chk_{cid}"
            last_star_ti = f"mix_star_last_ti_{cid}"
            if st.session_state.get(last_star_ti) != ti:
                st.session_state[chk_star] = ti in star_list
                st.session_state[last_star_ti] = ti

            def _on_mix_star_change() -> None:
                lst = _get_mix_star_index_list(cid)
                idx = int(st.session_state.get(last_star_ti) or 0)
                if bool(st.session_state.get(chk_star)):
                    if idx not in lst:
                        lst.append(idx)
                else:
                    while idx in lst:
                        lst.remove(idx)

            st.checkbox(
                "⭐ 다시 볼 표시 (헷갈림)",
                key=chk_star,
                on_change=_on_mix_star_change,
                help="체크한 문항은 오른쪽 전체 답안 목록에 ⭐로 보입니다. 문항을 옮겨도 유지됩니다.",
            )
            st.markdown("##### 보기")
            for ki in range(min(4, len(opts))):
                st.markdown(
                    f'<p style="margin:0.15rem 0;font-size:0.95rem;line-height:1.45;">'
                    f"<b>{marks[ki]}</b> {html.escape(str(opts[ki]))}</p>",
                    unsafe_allow_html=True,
                )
            cur_pick = _int_answer(st.session_state.get(f"stu_mix_q_{cid}_{ti}"))
            pick_cols = st.columns(4)
            for k in range(4):
                with pick_cols[k]:
                    if st.button(
                        marks[k],
                        key=f"mix_pick_{cid}_{ti}_{k}",
                        type="primary" if cur_pick == k else "secondary",
                        use_container_width=True,
                        help=str(opts[k])[:240] if k < len(opts) else "",
                    ):
                        st.session_state[f"stu_mix_q_{cid}_{ti}"] = k
                        st.rerun()
            st.caption("오른쪽 **전체 답안**에서 문항을 누르면 이동합니다.")
            prev_c, mid_c, next_c = st.columns([1, 1.2, 1])
            with prev_c:
                if st.button(
                    "← 이전",
                    key=f"mix_prev_{cid}",
                    disabled=ti <= 0,
                    use_container_width=True,
                ):
                    st.session_state[idx_key] = ti - 1
                    st.rerun()
            with mid_c:
                st.markdown(
                    f"<div style='text-align:center;font-size:0.95rem;padding:0.35rem 0 0 0;'>"
                    f"<strong>{ti + 1}</strong> / {n_q}</div>",
                    unsafe_allow_html=True,
                )
            with next_c:
                if st.button(
                    "다음 →",
                    key=f"mix_next_{cid}",
                    disabled=ti >= n_q - 1,
                    use_container_width=True,
                ):
                    st.session_state[idx_key] = ti + 1
                    st.rerun()

        row_cancel, row_grade = st.columns([1, 1.15])
        with row_cancel:
            if st.button("취소하고 나가기", key=f"mix_cancel_{cid}", use_container_width=True):
                _clear_mix_keys(cid, len(session))
                st.session_state[STUDENT_QUIZ_MIX_PHASE] = "setup"
                st.rerun()
        with row_grade:
            if st.button(
                "채점·해설 보기",
                key=f"mix_submit_{cid}",
                type="primary",
                use_container_width=True,
                help="모든 문항에 보기를 선택했는지 확인한 뒤 채점·AI 해설로 넘어갑니다.",
            ):
                miss = _unanswered_question_nums(cid, n_q)
                if miss:
                    st.warning(
                        "아직 보기를 고르지 않은 문항이 있습니다: "
                        + ", ".join(f"{x}번" for x in miss)
                    )
                else:
                    answers = [
                        _int_answer(st.session_state.get(f"stu_mix_q_{cid}_{j}"))
                        for j in range(len(session))
                    ]
                    blocks: list[str] = []
                    for j, it in enumerate(session):
                        cor = int(it.get("correct") or 0)
                        ok = answers[j] == cor
                        wt = str(it.get("week_title") or "")
                        qtxt = str(it.get("text") or "")[:400]
                        ua = answers[j]
                        u_lab = marks[ua] if 0 <= ua < len(marks) else "?"
                        c_lab = marks[cor] if cor < len(marks) else "?"
                        blocks.append(
                            f"- 문항{j+1} [{wt}] {'정답' if ok else '오답'}\n"
                            f"  지문: {qtxt}\n"
                            f"  선택: {u_lab} / 정답: {c_lab}\n"
                            f"  등록해설: {(str(it.get('explanation') or '').strip() or '(없음)')[:300]}"
                        )
                    block_s = "\n".join(blocks)
                    review_md = ""
                    if gemini_client.get_api_key():
                        try:
                            with st.spinner("Gemini가 해설·보완점을 정리하는 중…"):
                                review_md = gemini_client.explain_mixed_quiz_practice(
                                    course_name=course_name,
                                    question_blocks=block_s,
                                    usage={
                                        "org_id": org_id,
                                        "category_id": category_id,
                                        "bucket": "student_quiz",
                                        "usage_kind": "student_quiz_mixed_review",
                                    },
                                )
                        except Exception as e:
                            review_md = "(AI 해설을 생성하지 못했습니다. 아래 문항별 해설을 확인하세요.)"
                            err_s = str(e).lower()
                            if "429" in err_s or "quota" in err_s or "resource exhausted" in err_s:
                                st.error(gemini_client.format_quota_error_message(e))
                            else:
                                st.error(f"AI 해설 생성에 실패했습니다: {e}")
                    else:
                        ui_messages.warn_gemini_key_missing()
                        review_md = (
                            f"(로컬 요약) 정답 **{sum(1 for j, it in enumerate(session) if answers[j] == int(it.get('correct') or 0))}**/"
                            f"{len(session)}. Gemini 키가 있으면 위에 AI 총평이 표시됩니다."
                        )
                    st.session_state[sk_review] = review_md
                    if not st.session_state.get(f"mix_fs_batch_logged_{cid}"):
                        correct_n = sum(
                            1
                            for j, it in enumerate(session)
                            if answers[j] == int(it.get("correct") or 0)
                        )
                        items: list[dict[str, Any]] = []
                        for j, it in enumerate(session):
                            cor = int(it.get("correct") or 0)
                            ok = answers[j] == cor
                            items.append(
                                {
                                    "week_title": str(it.get("week_title") or ""),
                                    "week_doc_id": str(it.get("week_doc_id") or ""),
                                    "ok": ok,
                                    "question_preview": str(it.get("text") or "")[:500],
                                    "picked_index": int(answers[j]),
                                    "correct_index": cor,
                                }
                            )
                        _try_append_integrated_quiz_log(
                            org_id=org_id,
                            category_id=str(category_id),
                            course_name=course_name,
                            student_uid=student_uid,
                            student_email=student_email,
                            display_name=display_name,
                            event_type="batch_complete",
                            details={
                                "mode": "batch",
                                "n_questions": len(session),
                                "correct_n": correct_n,
                                "ai_review_md": str(review_md)[:12000],
                                "items": items,
                            },
                        )
                        st.session_state[f"mix_fs_batch_logged_{cid}"] = True
                    st.session_state[STUDENT_QUIZ_MIX_PHASE] = "done"
                    st.rerun()
        return

    # --- 설정 ---
    weeks = list_lesson_weeks(org_id, category_id)
    choices: list[dict[str, Any]] = []
    for w in weeks:
        if not week_in_student_list(w):
            continue
        wid = str(w.get("_doc_id") or "").strip()
        if not wid:
            continue
        if str(w.get("quiz_mode") or "off") == "off":
            continue
        wfull = get_lesson_week(org_id, category_id, wid) or w
        if not quiz_pool_for_week(wfull):
            continue
        wi = int(w.get("week_index") or 0)
        wt = str(w.get("title") or f"{wi}주차")
        choices.append({"id": wid, "label": f"{wt} ({wi}주차)"})

    if not choices:
        st.info(
            "이 수업에서 **퀴즈가 켜져 있고 문항이 등록된 주차**가 없습니다. "
            "교사 **수업 관리**에서 주차별 퀴즈를 설정한 뒤 이용하세요."
        )
        return

    id_to_label = {c["id"]: c["label"] for c in choices}
    sel_ids = st.multiselect(
        "연습에 넣을 회차(주차) 선택 (복수 선택 가능)",
        options=[c["id"] for c in choices],
        format_func=lambda x: id_to_label.get(x, x),
        key=f"mix_weeks_{cid}",
    )

    pool_preview: list[dict[str, Any]] = []
    if sel_ids:
        pool_preview = _build_pool_for_weeks(org_id, category_id, list(sel_ids))
    st.caption(f"선택한 회차에서 가져올 수 있는 문항: **{len(pool_preview)}**개")

    st.radio(
        "연습 방식",
        ["batch", "infinite"],
        format_func=lambda x: (
            "일괄 연습 — 여러 문항을 모아 한 번에 채점·AI 해설"
            if x == "batch"
            else "무한 연습 — 한 문제씩 풀고 바로 정답·해설 (오답 비중 자동 조절)"
        ),
        key=f"mix_style_{cid}",
        horizontal=True,
    )
    _style = str(st.session_state.get(f"mix_style_{cid}") or "batch")

    if _style == "infinite":
        st.caption(
            "선택한 회차 **전체 문항 풀**에서 무작위로 한 문제씩 냅니다. "
            "같은 문항·같은 주차에서 오답이 쌓일수록 다음에 나올 확률이 올라갑니다."
        )
        if st.button(
            "무한 연습 시작",
            type="primary",
            key=f"mix_start_inf_{cid}",
            disabled=len(sel_ids) == 0 or len(pool_preview) == 0,
        ):
            _clear_mix_keys(cid, 64)
            st.session_state[f"mix_inf_week_ids_{cid}"] = list(sel_ids)
            st.session_state[f"mix_inf_wrong_{cid}"] = {}
            st.session_state[f"mix_inf_attempt_{cid}"] = {}
            st.session_state[f"mix_inf_week_wrong_{cid}"] = {}
            st.session_state[f"mix_inf_total_{cid}"] = 0
            st.session_state[f"mix_inf_ai_md_{cid}"] = ""
            st.session_state[f"mix_inf_sub_{cid}"] = "answer"
            st.session_state.pop(f"mix_inf_cur_{cid}", None)
            st.session_state.pop(f"mix_inf_sel_{cid}", None)
            st.session_state[f"mix_inf_started_{cid}"] = time.time()
            st.session_state[STUDENT_QUIZ_MIX_PHASE] = "inf_run"
            st.rerun()
        return

    max_n = max(1, min(50, len(pool_preview)))
    n_q = st.number_input(
        "출제 문항 수",
        min_value=1,
        max_value=max_n,
        value=min(10, max_n),
        step=1,
        key=f"mix_nq_{cid}",
        help="무작위로 섞어 위 개수만큼 출제합니다.",
    )

    if st.button(
        "퀴즈 풀기",
        type="primary",
        key=f"mix_start_{cid}",
        disabled=len(sel_ids) == 0 or len(pool_preview) == 0,
    ):
        _clear_mix_keys(cid, 64)
        pool = list(pool_preview)
        random.shuffle(pool)
        n_take = min(int(n_q), len(pool))
        session = pool[:n_take]
        st.session_state[sk_session] = session
        st.session_state.pop(sk_review, None)
        st.session_state[f"mix_started_{cid}"] = time.time()
        st.session_state[f"stu_mix_idx_{cid}"] = 0
        st.session_state[f"mix_style_{cid}"] = "batch"
        st.session_state[STUDENT_QUIZ_MIX_PHASE] = "run"
        st.rerun()
