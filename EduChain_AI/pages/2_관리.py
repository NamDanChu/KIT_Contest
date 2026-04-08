"""운영자: 학원·학교(기업) 목록·추가·선택 후 세부 설정."""

from __future__ import annotations

import html

import streamlit as st

from services.auth_admin import delete_auth_user, update_auth_user
from services.firestore_repo import (
    count_students_in_org,
    create_organization,
    delete_user_document,
    get_organization,
    list_organizations_by_owner,
    list_users_by_org,
    update_organization,
    update_user_fields,
)
from services.ai_usage_ui import render_org_ai_usage_dashboard
from services.mgmt_content import render_org_content_tab
from services.mgmt_people import render_org_people_tab
from services.plan_limits import PLAN_ORDER, max_slots_for_plan, normalize_plan
from services.sidebar_helpers import (
    hide_login_nav_when_authed,
    render_login_gate_with_intro,
    render_mgmt_detail_category_sidebar,
    render_sidebar_user_block,
)
from services.session_keys import (
    AUTH_ROLE,
    AUTH_UID,
    MGMT_DETAIL_TAB,
    MGMT_SELECTED_ORG_ID,
    MGMT_VIEW_MODE,
)

hide_login_nav_when_authed()

st.session_state.setdefault(MGMT_VIEW_MODE, "list")

if not st.session_state.get(AUTH_UID):
    render_login_gate_with_intro(
        title="관리",
        description=(
            "학원·학교(기업)를 **등록·선택**하고, 플랜·슬롯과 **교사·학생** 계정을 다루며, "
            "**콘텐츠 카테고리**에 교사를 배정하는 **운영자(Operator)** 전용 화면입니다.\n\n"
            "로그인 후 운영자 권한이 있는 계정으로만 이용할 수 있습니다."
        ),
        login_button_key="login_gate_mgmt",
    )

if st.session_state.get(AUTH_ROLE) != "Operator":
    st.error("운영자(Operator)만 이 메뉴를 사용할 수 있습니다.")
    st.stop()

uid = st.session_state[AUTH_UID]

# --- 세부 설정 화면 (기업 선택 후) — 사이드바: 네비 아래 카테고리 → 유저(역할 아래 기업명) ---
if (
    st.session_state.get(MGMT_VIEW_MODE) == "detail"
    and st.session_state.get(MGMT_SELECTED_ORG_ID)
):
    sel = str(st.session_state[MGMT_SELECTED_ORG_ID])
    detail = get_organization(sel)
    if not detail:
        st.error("기업 정보를 찾을 수 없습니다.")
        st.session_state[MGMT_VIEW_MODE] = "list"
        st.session_state.pop(MGMT_SELECTED_ORG_ID, None)
        st.rerun()

    org_name = str(detail.get("org_name", ""))

    render_mgmt_detail_category_sidebar()
    render_sidebar_user_block(
        logout_key="sidebar_logout_mgmt_detail",
        management_org_name=org_name,
    )

    tab_key = st.session_state.get(MGMT_DETAIL_TAB, "basic")

    if tab_key == "basic":
        st.subheader("기본 정보")
        with st.form(f"form_org_basic_{sel}"):
            name_in = st.text_input(
                "기업 표시 이름",
                value=org_name,
                key=f"basic_name_{sel}",
            )
            if st.form_submit_button("저장"):
                update_organization(sel, org_name=name_in.strip())
                st.success("저장했습니다.")
                st.rerun()

        _users = list_users_by_org(sel)

        def _role_label_ko(role: str) -> str:
            r = str(role or "")
            if r == "Teacher":
                return "교사"
            if r == "Student":
                return "학생"
            if r == "Operator":
                return "운영자"
            return r or "—"

        st.divider()
        st.markdown("##### 사용자")
        st.caption(
            "이 기업에 소속된 계정입니다. 초대·계정 생성은 **교사·학생** 메뉴에서 할 수 있습니다."
        )
        _q = (st.session_state.get(f"basic_user_search_{sel}") or "").strip().lower()
        st.text_input(
            "검색",
            key=f"basic_user_search_{sel}",
            placeholder="닉네임, 이메일, 역할(교사/학생/운영자)…",
        )

        def _user_matches_search(u: dict, query: str) -> bool:
            if not query:
                return True
            parts = [
                str(u.get("display_name") or "").lower(),
                str(u.get("email") or "").lower(),
                str(u.get("role") or "").lower(),
                _role_label_ko(str(u.get("role") or "")).lower(),
            ]
            return any(query in p for p in parts)

        _filtered = [u for u in _users if _user_matches_search(u, _q)]

        _sel_uid_key = f"mgmt_basic_selected_uid_{sel}"
        if _filtered:
            _h1, _h2, _h3, _h4 = st.columns([1.1, 2.2, 2.5, 0.9])
            with _h1:
                st.caption("**역할**")
            with _h2:
                st.caption("**닉네임**")
            with _h3:
                st.caption("**이메일**")
            with _h4:
                st.caption("**상세**")
            for u in _filtered:
                _uid_u = str(u.get("uid") or u.get("_doc_id") or "")
                _dn = str(u.get("display_name") or "").strip() or "(닉네임 없음)"
                _em = str(u.get("email") or "")
                _rl = _role_label_ko(str(u.get("role") or ""))
                c1, c2, c3, c4 = st.columns([1.1, 2.2, 2.5, 0.9])
                with c1:
                    st.write(_rl)
                with c2:
                    st.write(_dn)
                with c3:
                    st.write(_em)
                with c4:
                    if st.button(
                        "보기",
                        key=f"basic_ud_{sel}_{_uid_u}",
                        type="secondary",
                    ):
                        st.session_state[_sel_uid_key] = _uid_u
                        st.rerun()
        else:
            if _users:
                st.info("검색 조건에 맞는 사용자가 없습니다.")
            else:
                st.info("등록된 사용자가 없습니다.")

        _picked = st.session_state.get(_sel_uid_key)
        if _picked:
            _detail_u = next(
                (
                    x
                    for x in _users
                    if str(x.get("uid") or x.get("_doc_id") or "") == _picked
                ),
                None,
            )
            if _detail_u:

                def _mask_uid(u: str) -> str:
                    s = str(u)
                    if len(s) <= 8:
                        return "••••••••"
                    return f"{s[:4]} … {s[-4:]}"

                _cur_role = str(_detail_u.get("role") or "")
                _cur_dn = str(_detail_u.get("display_name") or "")
                _rev_key = f"mgmt_uid_reveal_{sel}_{_picked}"
                _mode_key = f"mgmt_basic_mode_{sel}_{_picked}"
                st.session_state.setdefault(_mode_key, "view")
                _mode = st.session_state.get(_mode_key, "view")

                _roles = ["Teacher", "Student", "Operator"]
                _k_dn = f"edit_dn_{sel}_{_picked}"
                _k_ro = f"edit_role_{sel}_{_picked}"
                _k_pw = f"edit_pw_{sel}_{_picked}"
                _k_pw2 = f"edit_pw2_{sel}_{_picked}"

                with st.expander("사용자 상세", expanded=True):
                    if _mode == "view":
                        st.markdown(
                            """
<style>
.mgmu-card {
  background: linear-gradient(165deg, #fafbfc 0%, #f0f3f7 100%);
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 1rem 1.15rem 1.1rem 1.15rem;
  margin-bottom: 0.65rem;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.mgmu-l {
  color: #64748b;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: -0.03em;
  text-transform: uppercase;
  margin-bottom: 0.35rem;
}
.mgmu-v {
  color: #0f172a;
  font-size: 1.05rem;
  font-weight: 600;
  line-height: 1.45;
  word-break: break-word;
}
.mgmu-sub {
  color: #94a3b8;
  font-size: 0.8rem;
  margin-top: 0.25rem;
}
.mgmu-card { max-width: 640px; }
</style>
                            """,
                            unsafe_allow_html=True,
                        )
                        _em = str(_detail_u.get("email") or "")
                        _oid = str(_detail_u.get("org_id") or "")
                        _blocks = [
                            (
                                "역할",
                                html.escape(_role_label_ko(_cur_role)),
                                html.escape(_cur_role),
                            ),
                            ("닉네임", html.escape(_cur_dn) if _cur_dn else "—", ""),
                            ("이메일", html.escape(_em), ""),
                            ("기업 ID", html.escape(_oid), ""),
                        ]
                        for _lbl, _main, _sub in _blocks:
                            _sub_html = (
                                f'<div class="mgmu-sub">코드: {_sub}</div>'
                                if _sub
                                else ""
                            )
                            st.markdown(
                                f'<div class="mgmu-card">'
                                f'<div class="mgmu-l">{_lbl}</div>'
                                f'<div class="mgmu-v">{_main}</div>{_sub_html}'
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                        st.markdown("**UID**")
                        _show_full = st.session_state.get(_rev_key, False)
                        u1, u2 = st.columns([4, 1])
                        with u1:
                            st.code(
                                _picked if _show_full else _mask_uid(_picked),
                                language=None,
                            )
                        with u2:
                            if not _show_full:
                                if st.button(
                                    "전체 보기",
                                    key=f"uid_show_{sel}_{_picked}",
                                ):
                                    st.session_state[_rev_key] = True
                                    st.rerun()
                            else:
                                if st.button(
                                    "숨기기",
                                    key=f"uid_hide_{sel}_{_picked}",
                                ):
                                    st.session_state[_rev_key] = False
                                    st.rerun()

                        bv1, bv2 = st.columns(2)
                        with bv1:
                            if st.button(
                                "상세정보변경",
                                key=f"basic_to_edit_{sel}_{_picked}",
                                type="primary",
                                use_container_width=True,
                            ):
                                st.session_state[_mode_key] = "edit"
                                if _k_dn not in st.session_state:
                                    st.session_state[_k_dn] = _cur_dn
                                if _k_ro not in st.session_state:
                                    st.session_state[_k_ro] = (
                                        _cur_role
                                        if _cur_role in _roles
                                        else "Student"
                                    )
                                st.rerun()
                        with bv2:
                            if st.button(
                                "상세 닫기",
                                key=f"basic_ud_close_{sel}",
                                use_container_width=True,
                            ):
                                st.session_state.pop(_sel_uid_key, None)
                                st.session_state.pop(_rev_key, None)
                                st.session_state.pop(_mode_key, None)
                                st.session_state.pop(_k_dn, None)
                                st.session_state.pop(_k_ro, None)
                                st.session_state.pop(_k_pw, None)
                                st.session_state.pop(_k_pw2, None)
                                st.session_state.pop(
                                    f"mgmt_del_confirm_{sel}_{_picked}",
                                    None,
                                )
                                st.rerun()

                    else:
                        st.caption("닉네임·역할·비밀번호를 수정할 수 있습니다. 비밀번호는 변경할 때만 입력하세요.")
                        if _k_dn not in st.session_state:
                            st.session_state[_k_dn] = _cur_dn
                        if _k_ro not in st.session_state:
                            st.session_state[_k_ro] = (
                                _cur_role
                                if _cur_role in _roles
                                else "Student"
                            )

                        with st.form(f"form_edit_user_{sel}_{_picked}"):
                            st.text_input("닉네임", key=_k_dn)
                            st.selectbox("역할", _roles, key=_k_ro)
                            st.text_input(
                                "새 비밀번호 (선택)",
                                type="password",
                                key=_k_pw,
                                placeholder="변경하지 않으려면 비워 두세요",
                            )
                            st.text_input(
                                "새 비밀번호 확인",
                                type="password",
                                key=_k_pw2,
                            )
                            _save_ed = st.form_submit_button(
                                "저장", type="primary"
                            )

                        if st.button(
                            "취소",
                            key=f"edit_cancel_{sel}_{_picked}",
                            use_container_width=True,
                        ):
                            st.session_state[_mode_key] = "view"
                            st.session_state.pop(_k_pw, None)
                            st.session_state.pop(_k_pw2, None)
                            st.rerun()

                        if _save_ed:
                            _dn_v = (st.session_state.get(_k_dn) or "").strip()
                            _role_v = st.session_state.get(_k_ro)
                            _pw1 = st.session_state.get(_k_pw) or ""
                            _pw2 = st.session_state.get(_k_pw2) or ""
                            _org = get_organization(sel) or {}
                            _max_s = int(_org.get("max_slots") or 0)
                            _n_stu = count_students_in_org(sel)
                            _was_stu = _cur_role == "Student"
                            _will_stu = _role_v == "Student"
                            _err = False
                            if _pw1 or _pw2:
                                if _pw1 != _pw2:
                                    st.error("새 비밀번호와 확인이 일치하지 않습니다.")
                                    _err = True
                                elif len(_pw1) < 6:
                                    st.error("비밀번호는 6자 이상이어야 합니다.")
                                    _err = True
                            if not _err:
                                if (
                                    _will_stu
                                    and not _was_stu
                                    and _n_stu >= _max_s
                                ):
                                    st.error(
                                        "학생 슬롯이 가득 차 역할을 학생으로 바꿀 수 없습니다."
                                    )
                                else:
                                    try:
                                        update_user_fields(
                                            _picked,
                                            display_name=_dn_v,
                                            role=str(_role_v),
                                        )
                                        update_auth_user(
                                            _picked,
                                            display_name=_dn_v,
                                            password=_pw1
                                            if (_pw1 and _pw1 == _pw2)
                                            else None,
                                        )
                                        st.session_state.pop(_k_pw, None)
                                        st.session_state.pop(_k_pw2, None)
                                        st.session_state[_mode_key] = "view"
                                        st.success("저장했습니다.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(str(e))

                        st.divider()
                        st.caption(
                            "계정 삭제 시 Firebase 인증과 Firestore 사용자 문서가 함께 제거됩니다. "
                            "복구할 수 없습니다."
                        )
                        if _picked == uid:
                            st.warning("본인 계정은 삭제할 수 없습니다.")
                        else:
                            _del_key = f"mgmt_del_confirm_{sel}_{_picked}"
                            if not st.session_state.get(_del_key):
                                if st.button(
                                    "계정 삭제",
                                    key=f"btn_del_user_{sel}_{_picked}",
                                    type="primary",
                                ):
                                    st.session_state[_del_key] = True
                                    st.rerun()
                            else:
                                st.error("정말 이 계정을 삭제할까요?")
                                d1, d2 = st.columns(2)
                                if d1.button(
                                    "취소",
                                    key=f"btn_del_cancel_{sel}_{_picked}",
                                ):
                                    st.session_state.pop(_del_key, None)
                                    st.rerun()
                                if d2.button(
                                    "삭제 확정",
                                    key=f"btn_del_ok_{sel}_{_picked}",
                                ):
                                    try:
                                        delete_auth_user(_picked)
                                        delete_user_document(_picked)
                                        st.session_state.pop(_del_key, None)
                                        st.session_state.pop(
                                            _sel_uid_key, None
                                        )
                                        st.session_state.pop(_rev_key, None)
                                        st.session_state.pop(_mode_key, None)
                                        st.session_state.pop(_k_dn, None)
                                        st.session_state.pop(_k_ro, None)
                                        st.session_state.pop(_k_pw, None)
                                        st.session_state.pop(_k_pw2, None)
                                        st.success("계정을 삭제했습니다.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(str(e))
            else:
                st.session_state.pop(_sel_uid_key, None)

    elif tab_key == "plan":
        st.subheader("플랜·슬롯")
        cur_plan = normalize_plan(str(detail.get("plan", "Starter")))
        plan_key = f"mgmt_plan_pick_{sel}"
        st.session_state.setdefault(plan_key, cur_plan)
        working = normalize_plan(str(st.session_state[plan_key]))
        st.session_state[plan_key] = working

        st.caption("요금제를 선택하면 해당 플랜의 최대 학생 수가 적용됩니다.")
        cols = st.columns(len(PLAN_ORDER))
        for i, pid in enumerate(PLAN_ORDER):
            with cols[i]:
                if st.button(
                    pid,
                    key=f"plan_btn_{sel}_{pid}",
                    type="primary" if working == pid else "secondary",
                    use_container_width=True,
                ):
                    if working != pid:
                        st.session_state[plan_key] = pid
                        st.rerun()

        cap = max_slots_for_plan(working)
        st.markdown(f"**최대 학생 수:** {cap}명")
        st.caption("플랜에 따라 자동으로 정해지며, 직접 수정할 수 없습니다.")

        if st.button("저장", key=f"save_plan_{sel}", type="primary"):
            update_organization(sel, plan=working, max_slots=cap)
            st.success("저장했습니다.")
            st.rerun()

    elif tab_key == "people":
        render_org_people_tab(sel, org_name)

    elif tab_key == "content":
        render_org_content_tab(sel, org_name)

    elif tab_key == "ai_usage":
        render_org_ai_usage_dashboard(sel)

    else:
        st.subheader("콘텐츠·통계")
        st.warning("알 수 없는 메뉴입니다.")

    st.stop()

# --- 목록 화면 ---
render_sidebar_user_block(logout_key="sidebar_logout_mgmt")

st.title("관리")

tab_list, tab_add = st.tabs(["내 학원·학교", "기업 추가"])

with tab_list:
    orgs = list_organizations_by_owner(uid)
    if not orgs:
        st.info("등록된 기업이 없습니다.")
    else:
        st.subheader("기업 목록")
        for o in orgs:
            oid = str(o.get("org_id") or o.get("_doc_id") or "")
            name = str(o.get("org_name") or "(이름 없음)")
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(f"**{name}**")
            with c2:
                if st.button("선택", key=f"pick_{oid}"):
                    st.session_state[MGMT_SELECTED_ORG_ID] = oid
                    st.session_state[MGMT_VIEW_MODE] = "detail"
                    st.session_state[MGMT_DETAIL_TAB] = "basic"
                    st.rerun()

with tab_add:
    st.caption("운영 중인 학원·학교(기업)를 추가로 등록합니다.")
    with st.form("form_new_org"):
        new_name = st.text_input("학원 / 학교(기업) 이름", key="new_org_name_input")
        submitted = st.form_submit_button("기업 등록", type="primary")

    if submitted:
        name = (st.session_state.get("new_org_name_input") or "").strip()
        if not name:
            st.error("이름을 입력하세요.")
        else:
            try:
                create_organization(org_name=name, owner_uid=uid)
                st.success("등록되었습니다.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
