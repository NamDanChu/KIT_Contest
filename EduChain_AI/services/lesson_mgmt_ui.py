"""교사 화면 — [수업 관리] 주차별 커리큘럼·Gemini·공개 설정."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, time, timezone

import pandas as pd
import streamlit as st

from services import gemini_client
from services.firestore_repo import (
    create_lesson_week,
    delete_lesson_week,
    ensure_lesson_week_indices_contiguous,
    ensure_lesson_weeks_seeded,
    get_lesson_week,
    list_lesson_weeks,
    list_student_lesson_questions_for_course,
    update_lesson_week,
)
from services.lesson_materials import build_combined_source_for_gemini
from services.quiz_items import normalize_quiz_items


def _quiz_txt_filename(course_title: str, week_doc_id: str, n: int) -> str:
    slug = re.sub(r"[^\w\s가-힣\-]+", "_", (course_title or "").strip())
    slug = slug[:40].strip("_") or "주차"
    wid = re.sub(r"[^\w\-]+", "", str(week_doc_id))[:16] or "week"
    return f"퀴즈_{slug}_{wid}_{n}문항.txt"


def _note_txt_filename(course_title: str, week_doc_id: str) -> str:
    slug = re.sub(r"[^\w\s가-힣\-]+", "_", (course_title or "").strip())
    slug = slug[:40].strip("_") or "주차"
    wid = re.sub(r"[^\w\-]+", "", str(week_doc_id))[:16] or "week"
    return f"한페이지요약_{slug}_{wid}.txt"


def _parse_iso_naive(s: str) -> datetime | None:
    if not s or not str(s).strip():
        return None
    try:
        return datetime.fromisoformat(str(s).strip())
    except Exception:
        return None


def _lm_sync_quiz_widgets_from_week(week: dict, category_id: str, sel_week_id: str) -> None:
    """DB 주차 문서 기준으로 퀴즈 위젯 session_state를 맞춘다."""
    qm = str(week.get("quiz_mode") or "off")
    if qm not in ("off", "open_anytime", "after_video"):
        qm = "off"
    qs = str(week.get("quiz_source") or "manual")
    if qs not in ("manual", "gemini"):
        qs = "manual"
    try:
        ic = int(week.get("quiz_item_count") or 5)
    except (TypeError, ValueError):
        ic = 5
    ic = max(1, min(50, ic))
    try:
        pm = int(week.get("quiz_pass_min") or ic)
    except (TypeError, ValueError):
        pm = ic
    pm = max(1, min(50, pm))
    pm = min(pm, ic)
    st.session_state[f"lm_quiz_mode_{category_id}_{sel_week_id}"] = qm
    st.session_state[f"lm_quiz_source_{category_id}_{sel_week_id}"] = qs
    st.session_state[f"lm_quiz_item_count_{category_id}_{sel_week_id}"] = ic
    st.session_state[f"lm_quiz_pass_min_{category_id}_{sel_week_id}"] = pm
    man = week.get("quiz_manual_items") or []
    if isinstance(man, list) and man:
        st.session_state[f"lm_quiz_manual_json_{category_id}_{sel_week_id}"] = json.dumps(
            man, ensure_ascii=False, indent=2
        )
    else:
        st.session_state[f"lm_quiz_manual_json_{category_id}_{sel_week_id}"] = "[]"


def _format_access_status(week: dict) -> str:
    mode = str(week.get("access_mode") or "open")
    if mode == "disabled":
        return "🔒 비활성 (숨김) — 학생 목록에서 제외"
    if mode == "inactive":
        return "⏸️ 비활성 (표시) — 학생에게 보이나 수강 불가"
    if mode == "open":
        return "🟢 열림 — 시간 제한 없음"
    s = _parse_iso_naive(str(week.get("window_start_iso") or ""))
    e = _parse_iso_naive(str(week.get("window_end_iso") or ""))
    now = datetime.now()
    if not s and not e:
        return "📅 예약 — 시작·종료 시각을 저장하세요."
    if s and now < s:
        return f"⏳ 예약 대기 — {s.strftime('%Y-%m-%d %H:%M')} 부터 열림"
    if e and now > e:
        return f"⏹️ 기간 종료 — {e.strftime('%Y-%m-%d %H:%M')} 에 닫힘"
    if s and e:
        return f"▶️ 열림 중 — {s.strftime('%m/%d %H:%M')} ~ {e.strftime('%m/%d %H:%M')}"
    if s:
        return f"▶️ 열림 중 — {s.strftime('%Y-%m-%d %H:%M')} 부터 (종료 미설정)"
    return "📅 예약"


def render_lesson_management_panel(
    *,
    org_id: str,
    category_id: str,
    course_name: str,
    plan_label: str,
    sub_item_id: str,
) -> None:
    ensure_lesson_weeks_seeded(org_id, category_id, default_weeks=3)
    weeks = list_lesson_weeks(org_id, category_id)
    if ensure_lesson_week_indices_contiguous(org_id, category_id):
        st.rerun()
    if not weeks:
        st.warning("주차 데이터를 만들 수 없습니다.")
        return

    id_to_week = {str(w.get("_doc_id") or ""): w for w in weeks if w.get("_doc_id")}
    ids = list(id_to_week.keys())
    labels = {
        wid: str(id_to_week[wid].get("title") or f"{id_to_week[wid].get('week_index', '')}주차")
        for wid in ids
    }

    # selectbox 키는 위젯 생성 *전에만* 바꿀 수 있음 → 주차 추가/삭제 후 선택은 pending 으로 넘김
    _sel_key = f"lm_week_sel_{category_id}"
    _pending_key = f"_lm_week_sel_pending_{category_id}"
    _pending = st.session_state.pop(_pending_key, None)
    if _pending is not None:
        if _pending in ids:
            st.session_state[_sel_key] = _pending
        elif ids:
            st.session_state[_sel_key] = ids[0]
    if ids and st.session_state.get(_sel_key) not in ids:
        st.session_state[_sel_key] = ids[0]

    top1, top2, top3 = st.columns([2, 1.6, 1.2])
    with top1:
        st.markdown(f"**과목** · {course_name}")
    with top2:
        sel_week_id = st.selectbox(
            "주차 선택",
            options=ids,
            format_func=lambda x: labels.get(x, x),
            key=_sel_key,
        )
    with top3:
        st.caption(f"요금제 · **{plan_label}**")
        if st.button("➕ 주차 추가", key=f"lm_add_week_{category_id}", help="맨 마지막 순번 다음 회차가 추가됩니다."):
            new_id = create_lesson_week(org_id, category_id)
            st.session_state[_pending_key] = new_id
            st.session_state.pop(f"lm_week_tracker_{category_id}", None)
            st.rerun()
        with st.expander("🗑️ 선택 주차 삭제", expanded=False):
            st.caption(
                f"현재 선택: **{labels.get(sel_week_id, sel_week_id)}** — 삭제 후 복구할 수 없습니다."
            )
            st.caption(
                "학습 목표, 업로드 기록, AI 요약·퀴즈·한 페이지 노트·키워드 등이 모두 삭제됩니다."
            )
            if st.button(
                "이 주차 삭제",
                key=f"lm_del_week_top_{category_id}_{sel_week_id}",
                type="primary",
            ):
                delete_lesson_week(org_id, category_id, sel_week_id)
                st.session_state.pop(f"lm_week_tracker_{category_id}", None)
                rest = list_lesson_weeks(org_id, category_id)
                if rest:
                    st.session_state[_pending_key] = str(rest[0].get("_doc_id"))
                else:
                    ensure_lesson_weeks_seeded(org_id, category_id, default_weeks=1)
                    rest2 = list_lesson_weeks(org_id, category_id)
                    if rest2:
                        st.session_state[_pending_key] = str(rest2[0].get("_doc_id"))
                st.rerun()

    # 목록 스냅샷이 아니라 문서 단건 조회로 최신 제목·학습목표 반영 (저장 후 다른 탭 갔다 오기 등)
    week = get_lesson_week(org_id, category_id, sel_week_id) or id_to_week.get(sel_week_id)
    if not week:
        st.error("주차 정보를 불러올 수 없습니다.")
        return

    widx = int(week.get("week_index") or 0)
    title = str(week.get("title") or f"{widx}주차")
    goals = str(week.get("learning_goals") or "")

    _wk_track = f"lm_week_tracker_{category_id}"
    _fp_key = f"lm_db_sync_fp_{category_id}_{sel_week_id}"
    db_fp = f"{title}\n{goals}"
    _quiz_fp_key = f"lm_quiz_db_fp_{category_id}_{sel_week_id}"
    _quiz_db_fp = json.dumps(
        {
            "m": week.get("quiz_mode"),
            "s": week.get("quiz_source"),
            "ic": week.get("quiz_item_count"),
            "pm": week.get("quiz_pass_min"),
            "man": week.get("quiz_manual_items"),
            "ai": week.get("quiz_ai_items"),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    if st.session_state.get(_wk_track) != sel_week_id:
        st.session_state[_wk_track] = sel_week_id
        st.session_state[_fp_key] = db_fp
        st.session_state[f"lm_goals_{category_id}_{sel_week_id}"] = goals
        st.session_state[f"lm_title_{category_id}_{sel_week_id}"] = title
        st.session_state[f"lm_video_url_{category_id}_{sel_week_id}"] = str(
            week.get("lesson_video_url") or ""
        )
        st.session_state[f"lm_live_chk_{category_id}_{sel_week_id}"] = bool(
            week.get("live_session_active")
        )
        st.session_state[_quiz_fp_key] = _quiz_db_fp
        _lm_sync_quiz_widgets_from_week(week, category_id, sel_week_id)
    elif st.session_state.get(_fp_key) != db_fp:
        # 같은 주차인데 DB가 바뀐 경우(저장 직후·다른 기기 등) → 입력칸을 DB와 맞춤
        st.session_state[_fp_key] = db_fp
        st.session_state[f"lm_goals_{category_id}_{sel_week_id}"] = goals
        st.session_state[f"lm_title_{category_id}_{sel_week_id}"] = title
        st.session_state[f"lm_video_url_{category_id}_{sel_week_id}"] = str(
            week.get("lesson_video_url") or ""
        )
        st.session_state[f"lm_live_chk_{category_id}_{sel_week_id}"] = bool(
            week.get("live_session_active")
        )
        st.session_state[_quiz_fp_key] = _quiz_db_fp
        _lm_sync_quiz_widgets_from_week(week, category_id, sel_week_id)
    elif st.session_state.get(_quiz_fp_key) != _quiz_db_fp:
        st.session_state[_quiz_fp_key] = _quiz_db_fp
        _lm_sync_quiz_widgets_from_week(week, category_id, sel_week_id)
    preview = str(week.get("ai_summary_preview") or "")
    sync = str(week.get("rag_sync_status") or "idle")
    uploads_meta = week.get("uploads_meta") or []
    if not isinstance(uploads_meta, list):
        uploads_meta = []
    keywords = str(week.get("keywords_extracted") or "")
    access_mode = str(week.get("access_mode") or "open")
    wstart = str(week.get("window_start_iso") or "")
    wend = str(week.get("window_end_iso") or "")

    st.caption(_format_access_status(week))

    st.markdown("##### 회차 제목 · 학습 목표 (AI 가이드라인)")
    title_in = st.text_input(
        "회차 제목 (목록에 표시)",
        key=f"lm_title_{category_id}_{sel_week_id}",
        placeholder=f"예: {widx}주차 · 일차함수 도입",
    )
    goals_in = st.text_area(
        "학습 목표 / 키워드",
        key=f"lm_goals_{category_id}_{sel_week_id}",
        height=110,
        placeholder="예: 일차함수의 그래프, 기울기와 y절편, 두 직선의 교점",
    )
    lesson_title = (title_in or "").strip() or title
    meta_hint = (
        f"org_id={org_id}, course_id={category_id}, week_id={sel_week_id}, "
        f"week_index={widx}, title={lesson_title}, sub_item_id={sub_item_id or '—'}"
    )
    st.caption(f"맥락 격리 메타 · `{meta_hint}`")

    c_save, _ = st.columns([1, 3])
    with c_save:
        if st.button(
            "제목·학습 목표 저장",
            key=f"lm_save_goals_{category_id}_{sel_week_id}",
            type="primary",
        ):
            update_lesson_week(
                org_id,
                category_id,
                sel_week_id,
                title=title_in,
                learning_goals=goals_in,
            )
            st.session_state[_pending_key] = sel_week_id
            st.success("저장했습니다.")
            st.rerun()

    st.markdown("##### 회차 공개 · 시청 가능 시간")
    st.caption(
        "**열림**: 제한 없음 · **기간 지정**: 시작~종료 사이에만 수강 가능 · "
        "**비활성(표시)**: 학생 목록에 보이나 수강 버튼 비활성 · "
        "**비활성(숨김)**: 학생 목록에서 아예 제외. 시각은 이 PC/서버 **로컬 시간** 기준입니다."
    )
    mode_labels = {
        "open": "열림 (시간 제한 없음)",
        "scheduled": "기간 지정",
        "inactive": "비활성 (표시) — 학생에게 보임, 수강 불가",
        "disabled": "비활성 (숨김) — 학생 목록에서 제외",
    }
    mode_order = ["open", "scheduled", "inactive", "disabled"]
    idx = mode_order.index(access_mode) if access_mode in mode_order else 0
    new_mode = st.radio(
        "공개 모드",
        options=mode_order,
        format_func=lambda m: mode_labels[m],
        index=idx,
        horizontal=True,
        key=f"lm_access_mode_{category_id}_{sel_week_id}",
    )

    ps = _parse_iso_naive(wstart)
    pe = _parse_iso_naive(wend)
    d_s = ps.date() if ps else None
    t_s = ps.time() if ps else None
    d_e = pe.date() if pe else None
    t_e = pe.time() if pe else None

    sd = d_s or date.today()
    st_time = t_s or time(9, 0)
    ed = d_e or date.today()
    en_time = t_e or time(23, 59)
    no_end = not bool(wend)

    if new_mode == "scheduled":
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            sd = st.date_input("시작일", value=sd, key=f"lm_ws_d_{category_id}_{sel_week_id}")
        with c2:
            st_time = st.time_input("시작 시각", value=st_time, key=f"lm_ws_t_{category_id}_{sel_week_id}")
        with c3:
            ed = st.date_input("종료일", value=ed, key=f"lm_we_d_{category_id}_{sel_week_id}")
        with c4:
            en_time = st.time_input("종료 시각", value=en_time, key=f"lm_we_t_{category_id}_{sel_week_id}")
        no_end = st.checkbox(
            "종료 없이 시작 이후 계속 열림",
            value=no_end,
            key=f"lm_no_end_{category_id}_{sel_week_id}",
        )

    if st.button("공개 설정 저장", key=f"lm_save_access_{category_id}_{sel_week_id}"):
        ws_iso = we_iso = ""
        if new_mode == "scheduled":
            ws_iso = datetime.combine(sd, st_time).isoformat()
            if not no_end:
                we_iso = datetime.combine(ed, en_time).isoformat()
        update_lesson_week(
            org_id,
            category_id,
            sel_week_id,
            access_mode=new_mode,
            window_start_iso=ws_iso if new_mode == "scheduled" else "",
            window_end_iso=we_iso if new_mode == "scheduled" else "",
        )
        st.session_state[_pending_key] = sel_week_id
        st.success("공개 설정을 저장했습니다.")
        st.rerun()

    st.markdown("##### 학생 수강 화면 (영상·라이브)")
    st.caption(
        "학생 **수업 수강** 화면 왼쪽에 재생됩니다. YouTube·Vimeo 공유 URL 또는 직접 재생 가능한 링크를 넣을 수 있습니다."
    )
    st.text_input(
        "수강 영상 URL",
        key=f"lm_video_url_{category_id}_{sel_week_id}",
        placeholder="https://www.youtube.com/watch?v=... 또는 https://vimeo.com/...",
    )
    st.checkbox(
        "라이브 세션 활성 (학생 화면에서 라이브 채팅 잠금 해제)",
        key=f"lm_live_chk_{category_id}_{sel_week_id}",
    )
    if st.button(
        "영상·라이브 설정 저장",
        key=f"lm_save_video_{category_id}_{sel_week_id}",
    ):
        update_lesson_week(
            org_id,
            category_id,
            sel_week_id,
            lesson_video_url=str(
                st.session_state.get(f"lm_video_url_{category_id}_{sel_week_id}") or ""
            ),
            live_session_active=bool(
                st.session_state.get(f"lm_live_chk_{category_id}_{sel_week_id}")
            ),
        )
        st.session_state[_pending_key] = sel_week_id
        st.success("영상·라이브 설정을 저장했습니다.")
        st.rerun()

    st.markdown("##### 학생 수강 — 퀴즈")
    st.caption(
        "**OFF**: 퀴즈 없음 · **처음부터**: 시청률과 무관하게 풀기 · **영상 100% 후**: 진행률 100%일 때만 풀기. "
        "문항은 **교사 직접(JSON)** 또는 **Gemini**로 등록합니다. (우측 «주차별 퀴즈 생성»은 TXT용 마크다운입니다.)"
    )
    _gem_fail_key = f"lm_gemini_quiz_fail_{category_id}_{sel_week_id}"
    _ai_items = week.get("quiz_ai_items") or []
    _n_ai = len(_ai_items) if isinstance(_ai_items, list) else 0
    st.markdown("**Gemini 객관식(JSON) 저장 상태**")
    if _n_ai > 0:
        st.success(
            f"Firestore에 **{_n_ai}**개 문항이 저장되어 있습니다. 학생 화면에서 출제·채점에 사용됩니다."
        )
    else:
        st.info(
            "아직 Gemini로 생성·저장된 문항이 **없습니다**. 아래 **「Gemini로 객관식 문항 생성·저장」**을 누르면 여기에 개수가 표시됩니다."
        )
    _last_fail = st.session_state.get(_gem_fail_key)
    if _last_fail:
        st.error(f"**직전 Gemini 생성 실패:** {_last_fail}")
    gem_ok = bool(gemini_client.get_api_key())
    qm_order = ["off", "open_anytime", "after_video"]
    qm_labels = {
        "off": "퀴즈 OFF",
        "open_anytime": "퀴즈 ON (처음부터)",
        "after_video": "퀴즈 ON (영상 시청 100% 후)",
    }
    st.selectbox(
        "퀴즈 모드",
        options=qm_order,
        format_func=lambda x: qm_labels[x],
        key=f"lm_quiz_mode_{category_id}_{sel_week_id}",
    )
    st.number_input(
        "출제·채점에 사용할 문항 수 (풀에 있는 문항 앞에서부터)",
        min_value=1,
        max_value=50,
        step=1,
        key=f"lm_quiz_item_count_{category_id}_{sel_week_id}",
        help="등록된 문항이 이보다 적으면 있는 만큼만 출제됩니다.",
    )
    _ic_for_pm = int(
        st.session_state.get(f"lm_quiz_item_count_{category_id}_{sel_week_id}") or 5
    )
    _ic_for_pm = max(1, min(50, _ic_for_pm))
    st.number_input(
        "통과에 필요한 정답 개수",
        min_value=1,
        max_value=_ic_for_pm,
        step=1,
        key=f"lm_quiz_pass_min_{category_id}_{sel_week_id}",
        help="이 개수 이상 맞추면 통과로 기록됩니다.",
    )
    qs_order = ["manual", "gemini"]
    qs_labels = {"manual": "교사 직접 (JSON)", "gemini": "Gemini 자동 출제 (JSON)"}
    st.radio(
        "출제 방식",
        options=qs_order,
        format_func=lambda x: qs_labels[x],
        horizontal=True,
        key=f"lm_quiz_source_{category_id}_{sel_week_id}",
    )
    st.text_area(
        "교사 출제 문항 JSON (quiz_source=교사일 때 저장)",
        key=f"lm_quiz_manual_json_{category_id}_{sel_week_id}",
        height=180,
        placeholder='[{"text":"문항","options":["가","나","다","라"],"correct":0,"explanation":"해설(선택)"}]',
    )
    ctx_quiz = st.session_state.get(f"lm_tool_ctx_{category_id}_{sel_week_id}") or ""
    if not ctx_quiz:
        ctx_quiz = f"{goals_in}\n\n{preview}"
    _gem_replace_ok_key = f"lm_gemini_replace_ok_{category_id}_{sel_week_id}"
    if _n_ai > 0:
        st.warning(
            f"이미 **{_n_ai}**개의 Gemini 문항이 저장되어 있습니다. "
            "다시 생성하면 **기존 문항이 삭제되고** 새 세트로 덮어씁니다."
        )
        st.checkbox(
            "기존 Gemini 문항을 삭제하고 새로 출제합니다",
            value=False,
            key=_gem_replace_ok_key,
        )

    q_save1, q_save2 = st.columns(2)
    with q_save1:
        if st.button(
            "퀴즈 설정 저장",
            key=f"lm_save_quiz_cfg_{category_id}_{sel_week_id}",
        ):
            qm = str(st.session_state.get(f"lm_quiz_mode_{category_id}_{sel_week_id}") or "off")
            if qm not in qm_order:
                qm = "off"
            qs = str(st.session_state.get(f"lm_quiz_source_{category_id}_{sel_week_id}") or "manual")
            if qs not in qs_order:
                qs = "manual"
            try:
                ic = int(st.session_state.get(f"lm_quiz_item_count_{category_id}_{sel_week_id}") or 5)
            except (TypeError, ValueError):
                ic = 5
            ic = max(1, min(50, ic))
            try:
                pm = int(st.session_state.get(f"lm_quiz_pass_min_{category_id}_{sel_week_id}") or ic)
            except (TypeError, ValueError):
                pm = ic
            pm = max(1, min(ic, pm))
            manual_raw = str(
                st.session_state.get(f"lm_quiz_manual_json_{category_id}_{sel_week_id}") or ""
            ).strip()
            if qs == "gemini":
                update_lesson_week(
                    org_id,
                    category_id,
                    sel_week_id,
                    quiz_mode=qm,
                    quiz_source=qs,
                    quiz_item_count=ic,
                    quiz_pass_min=pm,
                )
                st.session_state.pop(_gem_fail_key, None)
                st.session_state[_pending_key] = sel_week_id
                st.success("퀴즈 설정을 저장했습니다. (Gemini 문항은 «생성·저장»으로 갱신)")
                st.rerun()
            try:
                parsed = json.loads(manual_raw) if manual_raw else []
            except json.JSONDecodeError as e:
                st.error(f"JSON 형식 오류: {e}")
            else:
                try:
                    manual_items = normalize_quiz_items(parsed)
                except ValueError as e:
                    st.error(str(e))
                else:
                    if qm != "off" and not manual_items:
                        st.error("퀴즈를 켠 상태에서는 교사 출제 문항이 최소 1개 이상 필요합니다.")
                    else:
                        if qm != "off" and manual_items and len(manual_items) < ic:
                            st.warning(
                                f"등록 문항({len(manual_items)}개)이 설정 문항 수({ic})보다 적습니다. "
                                "학생에게는 앞에서부터 있는 만큼만 출제됩니다."
                            )
                        sess_n = min(ic, len(manual_items)) if manual_items else 0
                        pm_eff = min(pm, sess_n) if sess_n else min(pm, ic)
                        update_lesson_week(
                            org_id,
                            category_id,
                            sel_week_id,
                            quiz_mode=qm,
                            quiz_source="manual",
                            quiz_item_count=ic,
                            quiz_pass_min=pm_eff,
                            quiz_manual_items=manual_items,
                        )
                        st.session_state.pop(_gem_fail_key, None)
                        st.session_state[_pending_key] = sel_week_id
                        st.success("퀴즈 설정을 저장했습니다.")
                        st.rerun()
    with q_save2:
        _can_run_gemini = gem_ok and (
            _n_ai == 0 or bool(st.session_state.get(_gem_replace_ok_key))
        )
        if st.button(
            "Gemini로 객관식 문항 생성·저장",
            key=f"lm_gen_quiz_json_{category_id}_{sel_week_id}",
            disabled=not _can_run_gemini,
            help="문항이 이미 있으면 위의 동의에 체크한 뒤 누르면 기존 세트를 지우고 다시 출제합니다.",
        ):
            try:
                n = int(st.session_state.get(f"lm_quiz_item_count_{category_id}_{sel_week_id}") or 5)
            except (TypeError, ValueError):
                n = 5
            n = max(1, min(50, n))
            try:
                with st.spinner("Gemini가 객관식 JSON을 생성하는 중…"):
                    items = gemini_client.generate_quiz_items_json(
                        title=lesson_title,
                        learning_goals=goals_in,
                        source_text=ctx_quiz,
                        num_questions=n,
                    )
                try:
                    pm = int(
                        st.session_state.get(f"lm_quiz_pass_min_{category_id}_{sel_week_id}") or n
                    )
                except (TypeError, ValueError):
                    pm = n
                pm = max(1, min(n, pm))
                qm = str(st.session_state.get(f"lm_quiz_mode_{category_id}_{sel_week_id}") or "off")
                if qm not in qm_order:
                    qm = "off"
                update_lesson_week(
                    org_id,
                    category_id,
                    sel_week_id,
                    quiz_mode=qm,
                    quiz_source="gemini",
                    quiz_item_count=n,
                    quiz_pass_min=pm,
                    quiz_ai_items=items,
                )
                st.session_state.pop(_gem_fail_key, None)
                st.session_state[_pending_key] = sel_week_id
                try:
                    st.toast(
                        f"Gemini 문항 {len(items)}개 저장 완료",
                        icon="✅",
                    )
                except Exception:
                    pass
                st.rerun()
            except Exception as ex:
                st.session_state[_gem_fail_key] = str(ex)
                st.error(f"실패: {ex}")

    st.divider()

    left, mid, right = st.columns([1, 1.1, 1])

    with left:
        st.markdown("##### 지식 주입")
        gem_ok = bool(gemini_client.get_api_key())
        if not gem_ok:
            st.warning("**GEMINI_API_KEY** 가 없으면 AI 요약·퀴즈가 동작하지 않습니다. `.streamlit/secrets.toml` 을 확인하세요.")
        else:
            st.caption(
                "무료 API는 **분·일당 토큰 한도**가 있습니다. 429가 나오면 잠시 뒤 재시도하거나 "
                "[한도 안내](https://ai.google.dev/gemini-api/docs/rate-limits)를 확인하세요."
            )
        up_pdf = st.file_uploader(
            "교안 PDF",
            type=["pdf"],
            key=f"lm_pdf_{category_id}_{sel_week_id}",
            accept_multiple_files=True,
        )
        up_txt = st.file_uploader(
            "자막·대본 (txt/md)",
            type=["txt", "md"],
            key=f"lm_txt_{category_id}_{sel_week_id}",
            accept_multiple_files=True,
        )
        up_vid = st.file_uploader(
            "영상 (메타만 저장 · 자막은 txt로 함께 올리면 학습 반영)",
            type=["mp4", "webm", "mov", "mkv"],
            key=f"lm_vid_{category_id}_{sel_week_id}",
            accept_multiple_files=True,
        )

        if st.button(
            "AI 지식 학습 시작 (Gemini 요약·키워드)",
            key=f"lm_rag_{category_id}_{sel_week_id}",
            type="primary",
            disabled=not gem_ok,
        ):
            pdf_parts = [(f.name, f.getvalue()) for f in (up_pdf or [])]
            txt_parts = [(f.name, f.getvalue()) for f in (up_txt or [])]
            video_names = [f.name for f in (up_vid or [])]
            combined, _meta_parts = build_combined_source_for_gemini(
                learning_goals=goals_in,
                pdf_parts=pdf_parts,
                txt_parts=txt_parts,
                video_names=video_names,
            )
            now = datetime.now(timezone.utc).isoformat()
            meta = list(uploads_meta)
            for f in up_pdf or []:
                meta.append({"filename": f.name, "kind": "pdf", "uploaded_at": now})
            for f in up_txt or []:
                meta.append({"filename": f.name, "kind": "text", "uploaded_at": now})
            for f in up_vid or []:
                meta.append({"filename": f.name, "kind": "video", "uploaded_at": now})

            if not combined.strip():
                st.error("PDF·txt 내용이 비었습니다. 파일을 선택했는지 확인하세요. (영상만 있는 경우 자막 txt를 함께 올려 주세요.)")
            else:
                try:
                    with st.status(
                        "🔄 AI 지식 학습 중… (창을 닫지 마세요)",
                        expanded=True,
                    ) as s:
                        try:
                            s.write("① 교안·자막·목표 텍스트 **병합** 완료")
                            s.write(
                                "② **Gemini 요약·키워드** 생성 중… (API **1회** 호출, 수십 초~1분 걸릴 수 있음)"
                            )
                            summary, kw = gemini_client.summarize_lesson_with_keywords_one_shot(
                                title=lesson_title,
                                learning_goals=goals_in,
                                source_text=combined,
                                meta_hint=meta_hint,
                            )
                            s.write("③ **Firestore** 저장 중…")
                            update_lesson_week(
                                org_id,
                                category_id,
                                sel_week_id,
                                learning_goals=goals_in,
                                uploads_meta=meta,
                                rag_sync_status="synced",
                                ai_summary_preview=summary,
                                keywords_extracted=kw,
                            )
                            st.session_state[f"lm_tool_ctx_{category_id}_{sel_week_id}"] = combined[:32000]
                            s.update(
                                label="✅ 요약·키워드 반영 완료",
                                state="complete",
                                expanded=False,
                            )
                        except Exception:
                            s.update(
                                label="❌ 처리 중 오류 (아래 메시지 확인)",
                                state="error",
                                expanded=True,
                            )
                            raise
                    st.session_state[_pending_key] = sel_week_id
                    st.success("Gemini 요약·키워드를 반영했습니다.")
                    st.rerun()
                except Exception as ex:
                    st.error(str(ex))

        if uploads_meta:
            st.caption("기록된 업로드 메타 (최근 8건)")
            for m in uploads_meta[-8:]:
                st.caption(f"- {m.get('filename')} · {m.get('kind', '')}")

    ctx_tools = st.session_state.get(f"lm_tool_ctx_{category_id}_{sel_week_id}") or ""
    if not ctx_tools:
        ctx_tools = f"{goals_in}\n\n{preview}"

    with mid:
        st.markdown("##### 이번 주차 핵심 (AI 분석 미리보기)")
        if sync == "synced" and preview:
            st.markdown(preview)
        elif sync == "idle":
            st.info(
                "자료를 올리고 **AI 지식 학습 시작**을 누르면 Gemini가 요약을 생성합니다. "
                "주차·org·course 메타가 함께 설계됩니다."
            )
        else:
            st.caption(preview or "—")

    with right:
        st.markdown("##### AI 도구 (Gemini)")
        st.caption(
            "아래 «주차별 퀴즈 생성»은 **마크다운·TXT 배포**용입니다. "
            "학생 화면에서 채점되는 퀴즈는 위 **학생 수강 — 퀴즈**에서 설정합니다."
        )
        _quiz_n_stored = int(week.get("ai_quiz_num_questions") or 0)
        n_quiz = st.number_input(
            "퀴즈 문항 수",
            min_value=1,
            max_value=25,
            value=_quiz_n_stored if _quiz_n_stored >= 1 else 5,
            step=1,
            key=f"lm_quiz_n_{category_id}_{sel_week_id}",
            disabled=not gem_ok,
            help="생성 시 Firestore에 저장되며, 나중에 다시 와도 TXT로 받을 수 있습니다.",
        )
        if st.button(
            "주차별 퀴즈 생성",
            key=f"lm_quiz_{category_id}_{sel_week_id}",
            disabled=not gem_ok,
            use_container_width=True,
        ):
            try:
                with st.spinner("🔄 Gemini가 퀴즈를 생성하는 중입니다…"):
                    qz = gemini_client.generate_quiz_markdown(
                        title=lesson_title,
                        learning_goals=goals_in,
                        source_text=ctx_tools,
                        num_questions=int(n_quiz),
                        difficulty="중",
                    )
                update_lesson_week(
                    org_id,
                    category_id,
                    sel_week_id,
                    ai_quiz_markdown=qz,
                    ai_quiz_num_questions=int(n_quiz),
                )
                st.session_state[_pending_key] = sel_week_id
                st.success("저장되었습니다. 아래 **TXT 다운로드**로 받을 수 있습니다.")
                st.rerun()
            except Exception as ex:
                st.error(str(ex))

        qz_saved = str(week.get("ai_quiz_markdown") or "").strip()
        n_for_name = int(week.get("ai_quiz_num_questions") or 0) or int(n_quiz)
        quiz_ready = bool(qz_saved)
        st.download_button(
            label="퀴즈 TXT 다운로드",
            data=qz_saved.encode("utf-8") if quiz_ready else b"",
            file_name=_quiz_txt_filename(lesson_title, sel_week_id, n_for_name)
            if quiz_ready
            else "quiz.txt",
            mime="text/plain; charset=utf-8",
            key=f"lm_quiz_dl_{category_id}_{sel_week_id}",
            disabled=not quiz_ready,
            use_container_width=True,
        )

        if st.button(
            "한 페이지 요약 노트",
            key=f"lm_note_{category_id}_{sel_week_id}",
            disabled=not gem_ok,
            use_container_width=True,
        ):
            try:
                with st.spinner("🔄 Gemini가 한 페이지 노트를 작성하는 중…"):
                    note = gemini_client.generate_one_page_note(
                        title=lesson_title,
                        learning_goals=goals_in,
                        source_text=ctx_tools,
                    )
                update_lesson_week(
                    org_id,
                    category_id,
                    sel_week_id,
                    ai_one_page_note=note,
                )
                st.session_state[_pending_key] = sel_week_id
                st.success("저장되었습니다. 아래 **TXT 다운로드**로 받을 수 있습니다.")
                st.rerun()
            except Exception as ex:
                st.error(str(ex))

        note_saved = str(week.get("ai_one_page_note") or "").strip()
        note_ready = bool(note_saved)
        st.download_button(
            label="한 페이지 요약 TXT 다운로드",
            data=note_saved.encode("utf-8") if note_ready else b"",
            file_name=_note_txt_filename(lesson_title, sel_week_id) if note_ready else "note.txt",
            mime="text/plain; charset=utf-8",
            key=f"lm_note_dl_{category_id}_{sel_week_id}",
            disabled=not note_ready,
            use_container_width=True,
        )

        if st.button(
            "핵심 키워드 추출 (재실행)",
            key=f"lm_kw_{category_id}_{sel_week_id}",
            disabled=not gem_ok,
            use_container_width=True,
        ):
            try:
                with st.spinner("🔄 Gemini가 키워드를 추출하는 중…"):
                    kw2 = gemini_client.extract_keywords_line(
                        learning_goals=goals_in,
                        source_text=ctx_tools,
                    )
                    update_lesson_week(
                        org_id,
                        category_id,
                        sel_week_id,
                        keywords_extracted=kw2,
                    )
                st.session_state[_pending_key] = sel_week_id
                st.success(kw2)
                st.rerun()
            except Exception as ex:
                st.error(str(ex))
        if keywords:
            st.caption(f"저장된 키워드: {keywords}")

    st.divider()
    st.markdown("##### 데이터 피드백 루프 (인사이트)")
    st.caption(
        "아래 **주차별 질문 빈도**는 이 수업에 저장된 **학생 AI 질문** 기준입니다. "
        "우측은 답변이 짧거나 ‘모르겠’류가 포함된 기록을 참고용으로 띄웁니다."
    )
    ins1, ins2 = st.columns(2)
    q_logs = list_student_lesson_questions_for_course(
        org_id, category_id, limit=300
    )
    with ins1:
        st.markdown("**주차별 질문 빈도**")
        if not weeks:
            st.caption("주차가 없습니다.")
        elif not q_logs:
            st.info("아직 저장된 학생 질문이 없습니다. 학생이 AI 채팅으로 질문하면 여기에 쌓입니다.")
            st.bar_chart(
                pd.DataFrame({"질문 수": [0] * len(weeks)}, index=[str(w.get("title") or f"{int(w.get('week_index') or 0)}주차") for w in weeks])
            )
        else:
            cnt = Counter(str(r.get("week_doc_id") or "") for r in q_logs)
            labels: list[str] = []
            vals: list[int] = []
            for w in weeks:
                wid = str(w.get("_doc_id") or "")
                lab = str(w.get("title") or f"{int(w.get('week_index') or 0)}주차")
                labels.append(lab)
                vals.append(int(cnt.get(wid, 0)))
            st.bar_chart(
                pd.DataFrame({"질문 수": vals}, index=labels)
            )
    with ins2:
        st.markdown("**보충·확인 후보 (휴리스틱)**")
        if not q_logs:
            st.warning(
                "· (데모) AI가 낮은 확신으로 답한 질문\n"
                "· '모르겠어요' 반복 → 보충 수업 후보\n\n"
                "질문 데이터가 쌓이면 오른쪽에 **답변이 짧은 기록** 등이 자동 표시됩니다."
            )
        else:
            short = [
                r
                for r in q_logs
                if len(str(r.get("answer") or "").strip()) < 120
            ]
            unsure = [
                r
                for r in q_logs
                if "모르겠" in str(r.get("answer") or "")
                or "알 수 없" in str(r.get("answer") or "")
            ]
            if short:
                st.warning(f"답변이 짧은 기록 **{len(short)}**건 (내용 보강·수업 후보)")
            if unsure:
                st.warning(f"‘모르겠’·불확실 표현이 포함된 답변 **{len(unsure)}**건")
            if not short and not unsure:
                st.success("짧은 답변·불확실 패턴이 두드러지지 않습니다. (참고용)")
            show_rows = (short + unsure)[:8]
            seen = set()
            for r in show_rows:
                key = str(r.get("_doc_id") or "") + str(r.get("question") or "")[:40]
                if key in seen:
                    continue
                seen.add(key)
                qtxt = str(r.get("question") or "").strip()
                st.caption(f"· {(qtxt[:120] + '…') if len(qtxt) > 120 else qtxt}")

    st.info(
        "**맥락 격리**로 주차별 AI 정확도를 높이고, **Gemini**로 출제·요약을 돕으며, "
        "**공개·기간**으로 수업 노출을 제어합니다."
    )
