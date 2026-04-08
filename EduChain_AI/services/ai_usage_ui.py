"""AI 토큰 활용량(AiTokenRollup / AiTokenEvents) — 교사·운영자 UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from services.firestore_repo import (
    AI_USAGE_BUCKETS,
    AI_USAGE_KIND_LABELS_KO,
    aggregate_ai_usage_buckets_for_org,
    aggregate_ai_usage_kinds_for_org,
    get_ai_token_rollup_doc,
    kind_metrics_from_rollup_doc,
    list_content_categories,
    list_recent_ai_token_events,
)

_BUCKET_LABELS_KO: dict[str, str] = {
    "teacher_lesson": "선생님 · 수업 도구 (요약·퀴즈·노트 등)",
    "teacher_profile": "선생님 · 학생 학습 분석",
    "teacher_course_stats": "선생님 · 수업 통계 AI",
    "student_chat": "학생 · 주차 질문/답변",
    "student_quiz": "학생 · 통합 퀴즈 (코칭·해설)",
    "operator": "운영 · 피드백 초안 등",
}

# 차트 축 라벨용 (짧게)
_BUCKET_SHORT_KO: dict[str, str] = {
    "teacher_lesson": "선생님·수업도구",
    "teacher_profile": "선생님·학생분석",
    "teacher_course_stats": "선생님·수업통계",
    "student_chat": "학생·질문",
    "student_quiz": "학생·통합퀴즈",
    "operator": "운영",
}

_BUCKET_HELP_MD = """
| 코드 | 설명 |
|------|------|
| `teacher_lesson` | 교사 **수업 관리** 화면에서 요약·키워드·퀴즈(JSON/MD)·한 페이지 노트 등 |
| `teacher_profile` | 교사 **학생 상세**에서 «학생 분석하기» AI |
| `teacher_course_stats` | 교사 **수업 통계**에서 «수업 통계 분석하기» AI |
| `student_chat` | 학생 **수강** 화면 주차별 AI 질문/답변 |
| `student_quiz` | 학생 **통합 퀴즈** 무한 연습 코칭·연습 후 AI 해설 |
| `operator` | 운영자 **콘텐츠·통계** 등에서 피드백 초안·(운영자가 실행한) 수업 분석 AI |
"""

_VIEW_OPTIONS = ("표로 보기", "차트로 보기", "둘 다 보기")

# 세부 기능 표·차트 순서 (사용자가 읽기 쉬운 순)
_KIND_DISPLAY_ORDER: tuple[str, ...] = (
    "lesson_summary_keywords",
    "lesson_quiz_json",
    "lesson_quiz_markdown",
    "lesson_one_page_note",
    "lesson_keywords_only",
    "student_week_ai_chat",
    "student_quiz_infinite_coach",
    "student_quiz_mixed_review",
    "teacher_student_profile",
    "teacher_course_analysis",
    "operator_course_analysis",
    "operator_feedback_draft",
    "other",
)


def _configure_matplotlib_korean() -> None:
    import matplotlib

    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["font.sans-serif"] = [
        "Malgun Gothic",
        "NanumGothic",
        "Apple SD Gothic Neo",
        "Noto Sans CJK KR",
        "DejaVu Sans",
    ]


def _streamlit_fallback_bar_stacked(
    labels: list[str],
    inp: list[int],
    outv: list[int],
    *,
    caption: str,
) -> None:
    """matplotlib 미설치 시 Streamlit 기본 차트(가로 옵션 있으면 사용)."""
    st.caption(caption)
    df = pd.DataFrame({"입력 토큰": inp, "출력 토큰": outv}, index=labels)
    try:
        st.bar_chart(df, horizontal=True, use_container_width=True)
    except TypeError:
        st.caption("*(세로 막대 표시 — `pip install matplotlib` 권장)*")
        st.bar_chart(df, use_container_width=True)


def _streamlit_fallback_bar_single(
    labels: list[str],
    values: list[int],
    *,
    caption: str,
) -> None:
    st.caption(caption)
    df = pd.DataFrame({"총 토큰(입+출)": values}, index=labels)
    try:
        st.bar_chart(df, horizontal=True, use_container_width=True)
    except TypeError:
        st.caption("*(세로 막대 표시 — `pip install matplotlib` 권장)*")
        st.bar_chart(df, use_container_width=True)


def _render_hbar_input_output(
    labels: list[str],
    inp: list[int],
    outv: list[int],
    *,
    caption: str,
) -> None:
    """가로 막대(입력 + 출력 스택) — X축 세로 라벨 문제를 피함."""
    if not labels or len(inp) != len(outv) or len(labels) != len(inp):
        return
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        _streamlit_fallback_bar_stacked(labels, inp, outv, caption=caption)
        return

    _configure_matplotlib_korean()
    n = len(labels)
    fig_h = max(2.8, min(22.0, 0.58 * n + 1.4))
    _, ax = plt.subplots(figsize=(10, fig_h))
    y = list(range(n))
    ax.barh(y, inp, height=0.62, color="#2c5282", label="입력 토큰")
    ax.barh(y, outv, height=0.62, left=inp, color="#90cdf4", label="출력 토큰")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel("토큰 수", fontsize=10)
    ax.invert_yaxis()
    ax.legend(loc="lower right", fontsize=9)
    plt.tight_layout()
    st.caption(caption)
    st.pyplot(plt.gcf(), clear_figure=True)
    plt.close("all")


def _render_hbar_single(
    labels: list[str],
    values: list[int],
    *,
    caption: str,
) -> None:
    if not labels or not values or len(labels) != len(values):
        return
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        _streamlit_fallback_bar_single(labels, values, caption=caption)
        return

    _configure_matplotlib_korean()
    n = len(labels)
    fig_h = max(2.5, min(20.0, 0.52 * n + 1.2))
    _, ax = plt.subplots(figsize=(10, fig_h))
    y = list(range(n))
    ax.barh(y, values, height=0.55, color="#3182ce")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel("토큰 수 (입+출)", fontsize=10)
    ax.invert_yaxis()
    plt.tight_layout()
    st.caption(caption)
    st.pyplot(plt.gcf(), clear_figure=True)
    plt.close("all")


def _user_query_match_blob(q: str, blob: str) -> bool:
    qq = (q or "").strip().lower()
    if not qq:
        return True
    return qq in (blob or "").lower()


def _filter_actor_summary_rows(
    rows: list[dict[str, Any]], q: str
) -> list[dict[str, Any]]:
    if not (q or "").strip():
        return rows
    out: list[dict[str, Any]] = []
    for r in rows:
        blob = f"{r.get('사용자', '')} {r.get('역할', '')}"
        if _user_query_match_blob(q, blob):
            out.append(r)
    return out


def _fmt_event_time(v: Any) -> str:
    if v is None:
        return "—"
    try:
        if hasattr(v, "timestamp"):
            return datetime.fromtimestamp(v.timestamp(), tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
    except Exception:
        pass
    try:
        s = str(v).strip()
        return s[:22] if s else "—"
    except Exception:
        return "—"


def _category_name_map(org_id: str) -> dict[str, str]:
    m: dict[str, str] = {}
    for c in list_content_categories(org_id):
        cid = str(c.get("_doc_id") or "")
        if cid:
            m[cid] = str(c.get("name") or "").strip() or cid
    return m


_ROLE_KO: dict[str, str] = {
    "Teacher": "교사",
    "Student": "학생",
    "Operator": "운영",
}


def _role_ko(role: str) -> str:
    r = (role or "").strip()
    return _ROLE_KO.get(r, r or "—")


def _event_actor_display(e: dict[str, Any]) -> str:
    dn = str(e.get("actor_display_name") or "").strip()
    role = _role_ko(str(e.get("actor_role") or ""))
    uid = str(e.get("actor_uid") or "").strip()
    if dn and role and role != "—":
        return f"{dn} ({role})"
    if dn:
        return dn
    if uid:
        return f"UID {uid[:10]}…" if len(uid) > 10 else f"UID {uid}"
    return "— (미기록)"


def _event_matches_user_query(e: dict[str, Any], q: str) -> bool:
    if not (q or "").strip():
        return True
    parts = [
        str(e.get("actor_display_name") or ""),
        str(e.get("actor_uid") or ""),
        str(e.get("actor_role") or ""),
        _event_actor_display(e),
    ]
    blob = " ".join(parts)
    return _user_query_match_blob(q, blob)


def aggregate_events_by_actor(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """이벤트 목록을 사용자(actor_uid)별로 합산."""
    by_uid: dict[str, dict[str, Any]] = {}
    for e in events:
        uid = str(e.get("actor_uid") or "").strip()
        if not uid:
            uid = "__none__"
        if uid not in by_uid:
            by_uid[uid] = {
                "display_name": "",
                "role": "",
                "prompt": 0,
                "completion": 0,
                "calls": 0,
            }
        m = by_uid[uid]
        if not m["display_name"] and e.get("actor_display_name"):
            m["display_name"] = str(e.get("actor_display_name") or "").strip()
        if not m["role"] and e.get("actor_role"):
            m["role"] = str(e.get("actor_role") or "").strip()
        m["prompt"] += int(e.get("prompt_tokens") or 0)
        m["completion"] += int(e.get("completion_tokens") or 0)
        m["calls"] += 1
    rows: list[dict[str, Any]] = []
    for uid_key, m in by_uid.items():
        dn = m["display_name"]
        role_s = _role_ko(m["role"])
        if uid_key == "__none__":
            label = "미기록 (로그인·배포 이전 호출)"
        elif dn:
            label = f"{dn} ({role_s})" if role_s != "—" else dn
        else:
            label = f"UID {uid_key[:10]}…" if len(uid_key) > 10 else uid_key
        rows.append(
            {
                "사용자": label,
                "역할": role_s if uid_key != "__none__" else "—",
                "입력 합계": m["prompt"],
                "출력 합계": m["completion"],
                "호출 수": m["calls"],
                "_tot": m["prompt"] + m["completion"],
            }
        )
    rows.sort(key=lambda r: -int(r["_tot"]))
    for r in rows:
        del r["_tot"]
    return rows


def _metrics_from_rollup_doc(doc: dict[str, Any]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for b in AI_USAGE_BUCKETS:
        out[b] = {
            "prompt": int(doc.get(f"{b}_prompt") or 0),
            "completion": int(doc.get(f"{b}_completion") or 0),
            "calls": int(doc.get(f"{b}_calls") or 0),
        }
    return out


def _metrics_to_table_rows(metrics: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for b in AI_USAGE_BUCKETS:
        t = metrics[b]
        p, c, n = t["prompt"], t["completion"], t["calls"]
        if p or c or n:
            rows.append(
                {
                    "구분": _BUCKET_LABELS_KO.get(b, b),
                    "입력(토큰)": p,
                    "출력(토큰)": c,
                    "호출 수": n,
                }
            )
    return rows


def _kind_metrics_to_rows(
    km: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for code in _KIND_DISPLAY_ORDER:
        if code not in km:
            continue
        m = km[code]
        rows.append(
            {
                "세부 기능": AI_USAGE_KIND_LABELS_KO.get(code, code),
                "입력(토큰)": m["prompt"],
                "출력(토큰)": m["completion"],
                "호출 수": m["calls"],
            }
        )
        seen.add(code)
    for code in sorted(km.keys()):
        if code in seen:
            continue
        m = km[code]
        rows.append(
            {
                "세부 기능": AI_USAGE_KIND_LABELS_KO.get(code, code),
                "입력(토큰)": m["prompt"],
                "출력(토큰)": m["completion"],
                "호출 수": m["calls"],
            }
        )
    return rows


def _show_kind_table_chart(
    km: dict[str, dict[str, int]],
    *,
    view: str,
    chart_caption: str,
) -> None:
    rows = _kind_metrics_to_rows(km)
    if not rows:
        st.info(
            "세부 기능 집계가 아직 없습니다. **새로 배포된 기록 방식** 이후 호출부터 "
            "퀴즈 생성·학생 질문 등으로 나뉘어 쌓입니다."
        )
        return
    if view in ("표로 보기", "둘 다 보기"):
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )
    if view in ("차트로 보기", "둘 다 보기"):
        labels_k: list[str] = []
        inp_k: list[int] = []
        out_k: list[int] = []
        order = [c for c in _KIND_DISPLAY_ORDER if c in km] + sorted(
            [c for c in km if c not in _KIND_DISPLAY_ORDER]
        )
        for code in order:
            m = km[code]
            p, c, n = m["prompt"], m["completion"], m["calls"]
            if p or c or n:
                labels_k.append(AI_USAGE_KIND_LABELS_KO.get(code, code))
                inp_k.append(p)
                out_k.append(c)
        if labels_k:
            _render_hbar_input_output(labels_k, inp_k, out_k, caption=chart_caption)


def _show_table_chart(
    *,
    metrics: dict[str, dict[str, int]],
    view: str,
    chart_caption: str,
) -> None:
    rows = _metrics_to_table_rows(metrics)
    if not rows:
        st.info("아직 기록된 사용량이 없습니다.")
        return
    if view in ("표로 보기", "둘 다 보기"):
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )
    if view in ("차트로 보기", "둘 다 보기"):
        labels_b: list[str] = []
        inp_b: list[int] = []
        out_b: list[int] = []
        for b in AI_USAGE_BUCKETS:
            t = metrics[b]
            p, c, n = t["prompt"], t["completion"], t["calls"]
            if p or c or n:
                labels_b.append(_BUCKET_SHORT_KO.get(b, b))
                inp_b.append(p)
                out_b.append(c)
        if labels_b:
            _render_hbar_input_output(labels_b, inp_b, out_b, caption=chart_caption)


def _render_recent_events_table(
    org_id: str,
    *,
    category_id: str | None,
    name_map: dict[str, str],
    limit_fetch: int,
    max_rows: int,
    user_query: str = "",
) -> None:
    st.markdown("##### 최근 호출 상세 (입·출력 출처)")
    st.caption(
        "각 행은 **Gemini API 호출 1회**입니다. **세부 기능**은 퀴즈 생성·학생 질문 등 구체 화면이며, "
        "**발생 위치(묶음)** 는 큰 구분입니다. **수업**은 콘텐츠 카테고리 이름입니다."
    )
    raw = list_recent_ai_token_events(org_id, limit=limit_fetch)
    if category_id:
        raw = [e for e in raw if str(e.get("category_id") or "") == category_id]
    if (user_query or "").strip():
        raw = [e for e in raw if _event_matches_user_query(e, user_query)]
    rows_out: list[dict[str, Any]] = []
    for e in raw[:max_rows]:
        bid = str(e.get("bucket") or "")
        cid = e.get("category_id")
        if cid and str(cid).strip():
            cname = name_map.get(str(cid).strip(), str(cid).strip()[:14])
        else:
            cname = "(기업 공통/미지정)"
        uk = str(e.get("usage_kind") or "").strip()
        kind_lbl = AI_USAGE_KIND_LABELS_KO.get(uk, uk or "—")
        rows_out.append(
            {
                "사용자": _event_actor_display(e),
                "시각(UTC)": _fmt_event_time(e.get("created_at")),
                "세부 기능": kind_lbl,
                "발생 위치(묶음)": _BUCKET_LABELS_KO.get(bid, bid or "—"),
                "수업": cname,
                "입력": int(e.get("prompt_tokens") or 0),
                "출력": int(e.get("completion_tokens") or 0),
                "모델": str(e.get("model") or "")[:80] or "—",
            }
        )
    if not rows_out:
        st.info(
            "표시할 호출 이력이 없습니다. 검색어를 바꾸거나, 이 기능 사용 이후부터 쌓인 기록을 확인하세요."
        )
        return
    st.dataframe(
        pd.DataFrame(rows_out),
        use_container_width=True,
        hide_index=True,
        column_config={
            "사용자": st.column_config.TextColumn("사용자", width="medium"),
            "세부 기능": st.column_config.TextColumn("세부 기능", width="large"),
            "발생 위치(묶음)": st.column_config.TextColumn(
                "발생 위치(묶음)", width="large"
            ),
        },
    )


def render_course_ai_usage_summary(
    *,
    org_id: str,
    category_id: str,
    operator_view: bool = False,
    show_title: bool = True,
) -> None:
    """선택한 수업(카테고리) 문서의 버킷별 누적 + 최근 이력."""
    if show_title:
        st.markdown("##### AI 토큰 활용량 (이 수업)")
    if operator_view:
        st.caption(
            "선택한 **수업**에 기록된 누적·이력입니다. 운영자 전용 기능은 **운영** 구분에 포함됩니다."
        )
    else:
        st.caption(
            "이 수업에 한해서만 집계됩니다. **수업 관리·학생 질문·통합 퀴즈·통계 AI** 등이 구분별로 나뉩니다."
        )
    with st.expander("용도(구분) 설명", expanded=False):
        st.markdown(_BUCKET_HELP_MD)

    vk = f"ai_usage_course_view_{org_id}_{category_id}"
    view = st.radio(
        "보기 방식",
        options=_VIEW_OPTIONS,
        index=2,
        horizontal=True,
        key=f"{vk}_mode",
    )
    user_q = st.text_input(
        "사용자 검색 (이름·역할·UID 일부)",
        "",
        key=f"{vk}_user_q",
        help="**사용자별 합계**와 **최근 호출** 표에 동시에 적용됩니다.",
    )

    doc = get_ai_token_rollup_doc(org_id, category_id)
    metrics = _metrics_from_rollup_doc(doc)
    _show_table_chart(
        metrics=metrics,
        view=view,
        chart_caption="용도별 **입력·출력 토큰** (해당 수업 누적)",
    )

    st.markdown("###### 세부 기능별 (이 수업)")
    st.caption(
        "예: **객관식 퀴즈 풀 생성**, **학생 수강·주차 AI 질문**, **수업 요약·키워드**, "
        "**통합 퀴즈 코칭** 등으로 나뉩니다."
    )
    km = kind_metrics_from_rollup_doc(doc)
    _show_kind_table_chart(
        km,
        view=view,
        chart_caption="세부 기능별 **입력·출력 토큰** (이 수업)",
    )

    nm = _category_name_map(org_id)
    st.markdown("##### 사용자별 사용량 (이 수업)")
    st.caption(
        "각 **로그인 계정**이 이 수업에서 AI를 호출한 양입니다. "
        "최근 이벤트 **최대 2000건** 범위에서 합산합니다."
    )
    raw_act = list_recent_ai_token_events(org_id, limit=2000)
    raw_act = [e for e in raw_act if str(e.get("category_id") or "") == category_id]
    act_rows = aggregate_events_by_actor(raw_act)
    act_rows = _filter_actor_summary_rows(act_rows, user_q)
    if act_rows:
        st.dataframe(
            pd.DataFrame(act_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "사용자": st.column_config.TextColumn("사용자", width="large"),
            },
        )
    else:
        st.info(
            "표시할 사용자가 없습니다. 검색어를 바꾸거나, 배포 후 호출부터 기록을 확인하세요."
        )

    _render_recent_events_table(
        org_id,
        category_id=category_id,
        name_map=nm,
        limit_fetch=2000,
        max_rows=80,
        user_query=user_q,
    )


def render_teacher_ai_usage_panel(
    *,
    org_id: str,
    category_id: str,
    course_name: str,
) -> None:
    """교사 전용 메뉴: 선택 수업의 AI 토큰·사용자별 사용량."""
    st.subheader("AI 토큰 활용량")
    st.caption(
        f"**{course_name}** 수업만 표시합니다. 운영 화면의 **AI 토큰 활용량** 과 동일한 데이터를 "
        "수업 단위로 좁혀 봅니다."
    )
    render_course_ai_usage_summary(
        org_id=org_id,
        category_id=category_id,
        operator_view=False,
        show_title=False,
    )


def render_org_ai_usage_dashboard(org_id: str) -> None:
    """운영자: 기업 전체 합산 + 수업별 + 최근 이력."""
    st.subheader("AI 토큰 활용량")
    st.caption(
        "기업에 속한 수업·기능에서 발생한 **Gemini 입력·출력 토큰**을 누적합니다. "
        "아래에서 **표·차트**를 골라 보거나, **최근 호출**에서 호출마다 어느 기능·수업에서 나왔는지 확인할 수 있습니다."
    )
    vk = f"ai_usage_org_view_{org_id}"
    user_q_org = st.text_input(
        "사용자 검색 (이름·역할·UID 일부)",
        "",
        key=f"{vk}_user_q",
        help="**사용자별 합계**와 **최근 호출** 표에 동시에 적용됩니다.",
    )
    with st.expander("용도(구분) 설명 — 입력·출력이 어디서 나왔는지", expanded=False):
        st.markdown(_BUCKET_HELP_MD)

    view = st.radio(
        "보기 방식",
        options=_VIEW_OPTIONS,
        index=2,
        horizontal=True,
        key=f"{vk}_mode",
    )

    totals = aggregate_ai_usage_buckets_for_org(org_id)
    metrics: dict[str, dict[str, int]] = {
        b: {
            "prompt": totals[b]["prompt"],
            "completion": totals[b]["completion"],
            "calls": totals[b]["calls"],
        }
        for b in AI_USAGE_BUCKETS
    }

    st.markdown("###### 기업 전체 (용도별 합계)")
    _show_table_chart(
        metrics=metrics,
        view=view,
        chart_caption="용도별 **입력·출력 토큰** 합계 (기업 내 모든 수업 합산)",
    )

    st.markdown("###### 기업 전체 (세부 기능별)")
    st.caption(
        "수업 관리의 **퀴즈·요약**, 학생 화면의 **AI 질문·퀴즈 도움**, 운영 **피드백 초안** 등 "
        "기능 단위로 합산합니다."
    )
    kind_org = aggregate_ai_usage_kinds_for_org(org_id)
    _show_kind_table_chart(
        kind_org,
        view=view,
        chart_caption="세부 기능별 **입력·출력 토큰** (기업 전체)",
    )

    cats = list_content_categories(org_id)
    per_rows: list[dict[str, Any]] = []
    chart_labels: list[str] = []
    chart_tot: list[int] = []
    for c in cats:
        cid = str(c.get("_doc_id") or "")
        if not cid:
            continue
        d = get_ai_token_rollup_doc(org_id, cid)
        tot_in = sum(int(d.get(f"{b}_prompt") or 0) for b in AI_USAGE_BUCKETS)
        tot_out = sum(int(d.get(f"{b}_completion") or 0) for b in AI_USAGE_BUCKETS)
        calls = sum(int(d.get(f"{b}_calls") or 0) for b in AI_USAGE_BUCKETS)
        if tot_in or tot_out or calls:
            title = str(c.get("name") or c.get("title") or "").strip() or cid
            per_rows.append(
                {
                    "수업": title,
                    "입력 합계": tot_in,
                    "출력 합계": tot_out,
                    "호출 합계": calls,
                }
            )
            short = title if len(title) <= 20 else title[:18] + "…"
            chart_labels.append(short)
            chart_tot.append(tot_in + tot_out)

    st.markdown("###### 수업별 합계 (기록이 있는 과목만)")
    if not per_rows:
        st.caption("수업별 누적이 아직 없습니다.")
    else:
        pdf = pd.DataFrame(per_rows)
        if view in ("표로 보기", "둘 다 보기"):
            st.dataframe(pdf, use_container_width=True, hide_index=True)
        if view in ("차트로 보기", "둘 다 보기"):
            _render_hbar_single(
                chart_labels,
                chart_tot,
                caption="수업별 **입력+출력 토큰** 합 (대략적 비교용)",
            )

    st.markdown("###### 수업별 — 세부 기능 (펼쳐서 확인)")
    st.caption(
        "각 수업에서 **무엇에 토큰이 쓰였는지**(퀴즈 생성, 학생 질문, 요약 등)를 봅니다."
    )
    _cat_rows = []
    for c in cats:
        cid = str(c.get("_doc_id") or "")
        if not cid:
            continue
        d = get_ai_token_rollup_doc(org_id, cid)
        tot_in = sum(int(d.get(f"{b}_prompt") or 0) for b in AI_USAGE_BUCKETS)
        tot_out = sum(int(d.get(f"{b}_completion") or 0) for b in AI_USAGE_BUCKETS)
        calls = sum(int(d.get(f"{b}_calls") or 0) for b in AI_USAGE_BUCKETS)
        if tot_in or tot_out or calls:
            title = str(c.get("name") or c.get("title") or "").strip() or cid
            km_c = kind_metrics_from_rollup_doc(d)
            _cat_rows.append((title, cid, km_c))

    if not _cat_rows:
        st.caption("세부 기능을 표시할 수업이 없습니다.")
    else:
        for title, _cid, km_c in _cat_rows:
            with st.expander(f"📚 {title} — 세부 기능", expanded=False):
                if not km_c:
                    st.caption("이 수업에는 아직 세부 기능 집계가 없습니다. (신규 호출부터 누적)")
                else:
                    if view in ("표로 보기", "둘 다 보기"):
                        st.dataframe(
                            pd.DataFrame(_kind_metrics_to_rows(km_c)),
                            use_container_width=True,
                            hide_index=True,
                        )
                    if view in ("차트로 보기", "둘 다 보기"):
                        lk: list[str] = []
                        ik: list[int] = []
                        ok: list[int] = []
                        ko = [c for c in _KIND_DISPLAY_ORDER if c in km_c] + sorted(
                            [c for c in km_c if c not in _KIND_DISPLAY_ORDER]
                        )
                        for code in ko:
                            m = km_c[code]
                            p, c2, n = m["prompt"], m["completion"], m["calls"]
                            if p or c2 or n:
                                lk.append(AI_USAGE_KIND_LABELS_KO.get(code, code))
                                ik.append(p)
                                ok.append(c2)
                        if lk:
                            _render_hbar_input_output(
                                lk,
                                ik,
                                ok,
                                caption=f"「{title}」세부 기능 — 입력·출력",
                            )

    st.markdown("###### 사용자별 합계 (기업)")
    st.caption(
        "기업 내 **모든 수업**을 합친 호출 주체(교사·학생·운영)별 사용량입니다. "
        "최근 이벤트 **최대 2000건** 범위에서 합산합니다."
    )
    raw_org = list_recent_ai_token_events(org_id, limit=2000)
    act_org = aggregate_events_by_actor(raw_org)
    act_org = _filter_actor_summary_rows(act_org, user_q_org)
    if act_org:
        st.dataframe(
            pd.DataFrame(act_org),
            use_container_width=True,
            hide_index=True,
            column_config={
                "사용자": st.column_config.TextColumn("사용자", width="large"),
            },
        )
    else:
        st.caption("표시할 사용자가 없습니다. 검색어를 바꾸거나 이벤트가 쌓인 뒤 다시 확인하세요.")

    nm = _category_name_map(org_id)
    _render_recent_events_table(
        org_id,
        category_id=None,
        name_map=nm,
        limit_fetch=2000,
        max_rows=150,
        user_query=user_q_org,
    )
