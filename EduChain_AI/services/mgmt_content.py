"""운영자 — 기업 세부 설정「콘텐츠·통계」중 콘텐츠(카테고리·교사 배치)."""

from __future__ import annotations

import streamlit as st

from services.course_stats_ui import render_course_statistics_panel
from services.firestore_repo import (
    create_content_category,
    delete_content_category,
    list_content_categories,
    list_users_by_org,
    summarize_org_learning_snapshot,
    update_content_category,
)


def _teacher_uid(u: dict) -> str:
    return str(u.get("uid") or u.get("_doc_id") or "")


def render_org_content_tab(org_id: str, org_name: str) -> None:
    st.subheader("콘텐츠")
    st.caption(
        f"**{org_name}** · 카테고리(수업·반·과목 영역)를 만들고, 소속 **교사**를 배치합니다. "
        "각 과목을 펼치면 **교사 화면과 동일한 수업 통계**를 보고, **교사·학생 피드백**을 남길 수 있습니다."
    )

    snap = summarize_org_learning_snapshot(org_id)
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("등록 과목 수", f"{snap['n_categories']}개")
    with m2:
        st.metric("소속 교사", f"{snap['n_teachers']}명")
    with m3:
        st.metric("소속 학생", f"{snap['n_students']}명")
    with m4:
        st.metric("누적 AI 질문(과목 합산·상한/과목)", f"{snap['total_ai_questions']}건")
    st.caption(
        "AI 질문 건수는 모든 과목의 저장된 질문 문서 수를 합산합니다(과목당 최대 500건까지 조회)."
    )

    users = list_users_by_org(org_id)
    teachers = [u for u in users if str(u.get("role") or "") == "Teacher"]
    t_labels = {
        _teacher_uid(u): f"{(u.get('display_name') or '').strip() or '이름 없음'}"
        f" · {u.get('email', '')}"
        for u in teachers
        if _teacher_uid(u)
    }
    valid_tuids = set(t_labels.keys())

    with st.form(f"frm_new_cat_{org_id}"):
        st.text_input("새 카테고리 이름", key=f"new_cat_name_{org_id}")
        add_sub = st.form_submit_button("카테고리 추가", type="primary")

    if add_sub:
        raw = (st.session_state.get(f"new_cat_name_{org_id}") or "").strip()
        if not raw:
            st.error("카테고리 이름을 입력하세요.")
        else:
            try:
                create_content_category(org_id, raw, description="")
                st.session_state.pop(f"new_cat_name_{org_id}", None)
                st.success("카테고리를 추가했습니다.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    cats = list_content_categories(org_id)
    if not cats:
        st.info("등록된 카테고리가 없습니다. 위에서 이름을 입력해 추가하세요.")
        if not teachers:
            st.warning(
                "이 기업에 **교사** 계정이 없습니다. "
                "「교사·학생」에서 초대하거나 계정을 만든 뒤 여기서 편성할 수 있습니다."
            )
        return

    if not teachers:
        st.warning(
            "배치할 **교사**가 없습니다. 「교사·학생」 메뉴에서 교사를 등록해 주세요."
        )

    st.markdown("##### 카테고리 목록")
    for c in cats:
        cid = str(c.get("_doc_id") or "")
        cname = str(c.get("name") or "(이름 없음)")
        stored = [x for x in (c.get("teacher_uids") or []) if x in valid_tuids]

        _k_nm = f"ct_nm_{org_id}_{cid}"
        _k_ms = f"ct_ms_{org_id}_{cid}"
        if _k_nm not in st.session_state:
            st.session_state[_k_nm] = cname
        st.session_state.setdefault(_k_ms, stored)

        with st.expander(f"**{cname}**", expanded=False):
            st.caption(f"문서 ID: `{cid}`")
            with st.expander("📊 과목 통계·운영 피드백 (교사 화면과 동일)", expanded=False):
                render_course_statistics_panel(
                    org_id=org_id,
                    category_id=cid,
                    course_name=cname,
                    operator_mode=True,
                )

            with st.form(f"frm_cat_save_{org_id}_{cid}"):
                st.text_input("카테고리 이름", key=_k_nm)
                st.multiselect(
                    "이 카테고리에 배치할 교사",
                    options=sorted(t_labels.keys()),
                    format_func=lambda x: t_labels.get(x, x),
                    key=_k_ms,
                    disabled=not bool(t_labels),
                )
                sub = st.form_submit_button("저장", type="primary")

            if sub:
                nm = (st.session_state.get(_k_nm) or "").strip()
                sel = list(st.session_state.get(_k_ms) or [])
                sel = [x for x in sel if x in valid_tuids]
                if not nm:
                    st.error("카테고리 이름을 비울 수 없습니다.")
                else:
                    try:
                        update_content_category(
                            org_id,
                            cid,
                            name=nm,
                            teacher_uids=sel,
                        )
                        st.session_state.pop(_k_nm, None)
                        st.session_state.pop(_k_ms, None)
                        st.success("저장했습니다.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            _dkey = f"ct_del_confirm_{org_id}_{cid}"
            if not st.session_state.get(_dkey):
                if st.button(
                    "이 카테고리 삭제",
                    key=f"ct_del_{org_id}_{cid}",
                    type="secondary",
                ):
                    st.session_state[_dkey] = True
                    st.rerun()
            else:
                st.error("이 카테고리를 삭제할까요? 교사 배치 정보도 함께 사라집니다.")
                c1, c2 = st.columns(2)
                if c1.button("취소", key=f"ct_del_cancel_{org_id}_{cid}"):
                    st.session_state.pop(_dkey, None)
                    st.rerun()
                if c2.button("삭제 확정", key=f"ct_del_ok_{org_id}_{cid}"):
                    try:
                        delete_content_category(org_id, cid)
                        st.session_state.pop(_dkey, None)
                        st.session_state.pop(_k_nm, None)
                        st.session_state.pop(_k_ms, None)
                        st.success("삭제했습니다.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
