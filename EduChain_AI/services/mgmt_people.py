"""운영자 — 기업 세부 설정「교사·학생」탭."""

from __future__ import annotations

import html
from typing import Any

import pandas as pd
import streamlit as st

from services.auth_admin import (
    create_email_password_user,
    delete_auth_user,
    update_auth_user,
)
from services.firestore_repo import (
    approve_org_join_request,
    count_students_in_org,
    delete_user_document,
    ensure_org_invite_codes,
    get_organization,
    get_user,
    list_pending_join_requests,
    list_users_by_org,
    regenerate_org_invite_code,
    reject_org_join_request,
    update_user_fields,
    upsert_user,
)
from services.session_keys import AUTH_UID


def _role_label_ko(role: str) -> str:
    r = str(role or "")
    if r == "Teacher":
        return "교사"
    if r == "Student":
        return "학생"
    if r == "Operator":
        return "운영자"
    if r == "User":
        return "유저"
    return r or "—"


def _user_row_uid(u: dict) -> str:
    return str(u.get("uid") or u.get("_doc_id") or "").strip()


def _mask_uid_short(u: str) -> str:
    s = str(u)
    if not s:
        return "—"
    if len(s) <= 8:
        return "••••••••"
    return f"{s[:4]} … {s[-4:]}"


def _dataframe_selection_rows(event: Any) -> list[int]:
    """st.dataframe(on_select=...) 반환값에서 선택 행 인덱스 추출."""
    if event is None:
        return []
    try:
        sel = getattr(event, "selection", None)
        if sel is None and isinstance(event, dict):
            sel = event.get("selection")
        if sel is None:
            return []
        rows = getattr(sel, "rows", None)
        if rows is None and isinstance(sel, dict):
            rows = sel.get("rows")
        if not rows:
            return []
        return [int(x) for x in rows]
    except (TypeError, ValueError, AttributeError):
        return []


def _login_invite_url(code: str) -> str:
    """공유용 초대 링크. secrets 의 APP_BASE_URL 이 있으면 전체 URL, 없으면 경로만."""
    base = ""
    try:
        if hasattr(st, "secrets") and "APP_BASE_URL" in st.secrets:
            base = str(st.secrets["APP_BASE_URL"]).strip().rstrip("/")
    except Exception:
        pass
    path = f"/Login?invite={code}"
    return f"{base}{path}" if base else path


def render_org_people_tab(org_id: str, org_name: str) -> None:
    st.subheader("교사·학생")

    codes = ensure_org_invite_codes(org_id)
    detail = get_organization(org_id) or {}
    max_slots = int(detail.get("max_slots") or 0)
    student_n = count_students_in_org(org_id)

    st.markdown(f"**{org_name}** · 학생 슬롯 사용: **{student_n}** / **{max_slots}**")

    st.markdown("##### 초대 코드")
    st.caption(
        "아래 **짧은 링크**를 보내면 로그인 페이지가 열리고 초대 코드가 자동으로 채워집니다. "
        "(전체 URL을 쓰려면 secrets 에 `APP_BASE_URL` 을 설정하세요.)"
    )
    ct = codes.get("teacher", "")
    cs = codes.get("student", "")
    c1, c2 = st.columns(2)
    with c1:
        st.caption("교사용 코드")
        st.code(ct or "(생성 중)", language=None)
        if ct:
            st.caption("공유 링크 (교사)")
            st.code(_login_invite_url(ct), language=None)
        if st.button("교사 코드 재발급", key=f"reg_teacher_{org_id}"):
            regenerate_org_invite_code(org_id, "teacher")
            st.success("교사 초대 코드를 바꿨습니다. 이전 코드는 더 이상 쓸 수 없습니다.")
            st.rerun()
    with c2:
        st.caption("학생용 코드")
        st.code(cs or "(생성 중)", language=None)
        if cs:
            st.caption("공유 링크 (학생)")
            st.code(_login_invite_url(cs), language=None)
        if st.button("학생 코드 재발급", key=f"reg_student_{org_id}"):
            regenerate_org_invite_code(org_id, "student")
            st.success("학생 초대 코드를 바꿨습니다. 이전 코드는 더 이상 쓸 수 없습니다.")
            st.rerun()

    st.divider()
    st.markdown("##### 가입 승인 대기")
    st.caption(
        "초대 코드로 **소속을 신청만 한** 계정입니다. **승인**해야 해당 기업의 교사·학생으로 등록됩니다."
    )
    pending = list_pending_join_requests(org_id)
    if not pending:
        st.caption("(대기 중인 요청이 없습니다.)")
    else:
        for pr in pending:
            uid_p = str(pr.get("uid") or pr.get("_doc_id") or "").strip()
            em = str(pr.get("email") or "")
            dn = str(pr.get("display_name") or "")
            rr = str(pr.get("requested_role") or "")
            st.markdown(f"**{rr}** · {dn or '(이름 없음)'} · `{em}`")
            ap_key = f"join_appr_{org_id}_{uid_p}"
            rj_key = f"join_rej_{org_id}_{uid_p}"
            c_ap, c_rj = st.columns(2)
            with c_ap:
                if st.button("승인", key=ap_key, type="primary", use_container_width=True):
                    try:
                        approve_org_join_request(org_id, uid_p)
                        st.success("승인했습니다.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with c_rj:
                if st.button("거절", key=rj_key, use_container_width=True):
                    try:
                        reject_org_join_request(org_id, uid_p)
                        st.success("거절했습니다.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    st.divider()
    st.markdown("##### 계정 직접 만들기")
    st.caption("이메일·임시 비밀번호로 계정을 만들면 해당 기업 소속 교사 또는 학생으로 등록됩니다.")
    with st.form(f"direct_create_{org_id}"):
        dc_email = st.text_input("이메일", key=f"dc_email_{org_id}")
        dc_pw = st.text_input("비밀번호", type="password", key=f"dc_pw_{org_id}")
        dc_name = st.text_input("닉네임(표시 이름)", key=f"dc_name_{org_id}")
        dc_role = st.selectbox("역할", ["Teacher", "Student"], key=f"dc_role_{org_id}")
        submitted = st.form_submit_button("계정 만들기", type="primary")

    if submitted:
        em = (st.session_state.get(f"dc_email_{org_id}") or "").strip()
        pw = st.session_state.get(f"dc_pw_{org_id}") or ""
        nick = (st.session_state.get(f"dc_name_{org_id}") or "").strip()
        role = st.session_state.get(f"dc_role_{org_id}") or "Student"
        if not em or not pw:
            st.error("이메일과 비밀번호를 입력하세요.")
        elif len(pw) < 6:
            st.error("비밀번호는 6자 이상이어야 합니다.")
        elif not nick:
            st.error("닉네임을 입력하세요.")
        else:
            org = get_organization(org_id)
            if not org:
                st.error("기업 정보를 찾을 수 없습니다.")
            elif role == "Student" and count_students_in_org(org_id) >= int(
                org.get("max_slots") or 0
            ):
                st.error("학생 슬롯이 가득 찼습니다.")
            else:
                try:
                    new_uid = create_email_password_user(
                        em, pw, display_name=nick
                    )
                    upsert_user(new_uid, em, role, org_id, display_name=nick)
                    st.success("계정을 만들었습니다. 해당 이메일로 로그인할 수 있습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    st.divider()
    st.markdown("##### 소속 사용자 목록")
    st.caption(
        "표는 **스크롤** 가능합니다. **검색**으로 이름·이메일·역할·ID 를 걸러 내고, "
        "**정렬 기준**을 바꿔 목록을 정돈할 수 있습니다."
    )
    users = list_users_by_org(org_id)
    if not users:
        st.info("아직 등록된 교사·학생이 없습니다.")
    else:
        st.text_input(
            "검색",
            key=f"people_search_{org_id}",
            placeholder="닉네임, 이메일, 역할(영문/한글), 사용자 ID 일부…",
        )
        c_sk, c_dir = st.columns(2)
        with c_sk:
            st.selectbox(
                "정렬 기준",
                ["역할", "표시 이름", "이메일", "사용자 ID"],
                key=f"people_sort_key_{org_id}",
            )
        with c_dir:
            st.selectbox(
                "순서",
                ["오름차순", "내림차순"],
                key=f"people_sort_dir_{org_id}",
            )

        q = (st.session_state.get(f"people_search_{org_id}") or "").strip().lower()

        def _matches(u: dict, query: str) -> bool:
            if not query:
                return True
            uid_s = _user_row_uid(u)
            parts = [
                str(u.get("display_name") or "").lower(),
                str(u.get("email") or "").lower(),
                str(u.get("role") or "").lower(),
                _role_label_ko(str(u.get("role") or "")).lower(),
                uid_s.lower(),
            ]
            return any(query in p for p in parts)

        filtered: list[dict] = [u for u in users if _matches(u, q)]

        sk = str(st.session_state.get(f"people_sort_key_{org_id}") or "역할")
        rev = str(st.session_state.get(f"people_sort_dir_{org_id}") or "오름차순") == "내림차순"

        def _sort_tuple(u: dict) -> tuple:
            r_ko = _role_label_ko(str(u.get("role") or ""))
            dn = str(u.get("display_name") or "").lower()
            em = str(u.get("email") or "").lower()
            uid = _user_row_uid(u).lower()
            if sk == "표시 이름":
                return (dn, uid)
            if sk == "이메일":
                return (em, uid)
            if sk == "사용자 ID":
                return (uid,)
            return (r_ko, dn, em)

        filtered.sort(key=_sort_tuple, reverse=rev)

        if not filtered:
            st.info("검색 조건에 맞는 사용자가 없습니다.")
        else:
            rows: list[dict[str, str]] = []
            for u in filtered:
                uid_full = _user_row_uid(u)
                rows.append(
                    {
                        "역할": _role_label_ko(str(u.get("role") or "")),
                        "표시 이름": str(u.get("display_name") or "").strip() or "—",
                        "이메일": str(u.get("email") or ""),
                        "사용자 ID": _mask_uid_short(uid_full),
                    }
                )
            df = pd.DataFrame(rows)
            st.caption("표에서 **행을 클릭**하면 아래 「상세 정보를 볼 계정」이 같은 사용자로 바뀝니다.")
            _df_key = f"people_df_{org_id}"
            _cfg = {
                "역할": st.column_config.TextColumn("역할", width="small"),
                "표시 이름": st.column_config.TextColumn("표시 이름", width="medium"),
                "이메일": st.column_config.TextColumn("이메일", width="large"),
                "사용자 ID": st.column_config.TextColumn("사용자 ID", width="medium"),
            }
            df_event: Any = None
            try:
                df_event = st.dataframe(
                    df,
                    width="stretch",
                    height=400,
                    hide_index=True,
                    column_config=_cfg,
                    key=_df_key,
                    on_select="rerun",
                    selection_mode="single-row",
                )
            except TypeError:
                st.dataframe(
                    df,
                    use_container_width=True,
                    height=400,
                    hide_index=True,
                    column_config=_cfg,
                )

            _sel_rows = _dataframe_selection_rows(df_event)
            if _sel_rows:
                _ri = _sel_rows[0]
                if 0 <= _ri < len(filtered):
                    st.session_state[f"people_detail_sel_{org_id}"] = _user_row_uid(
                        filtered[_ri]
                    )

            def _fmt_pick(uid: str) -> str:
                uu = next((x for x in filtered if _user_row_uid(x) == uid), None)
                if not uu:
                    return uid
                return (
                    f"{_role_label_ko(str(uu.get('role') or ''))} · "
                    f"{str(uu.get('display_name') or '').strip() or '(이름 없음)'} · "
                    f"{str(uu.get('email') or '')}"
                )

            uids_ordered = [_user_row_uid(u) for u in filtered]
            sel = st.selectbox(
                "상세 정보를 볼 계정",
                options=uids_ordered,
                format_func=_fmt_pick,
                key=f"people_detail_sel_{org_id}",
            )
            u_sel = next((x for x in filtered if _user_row_uid(x) == sel), None)
            if u_sel:
                _puid = _user_row_uid(u_sel)
                _roles_edit = ["Teacher", "Student", "Operator"]
                mode_key = f"people_umode_{org_id}_{_puid}"
                st.session_state.setdefault(mode_key, "view")
                _umode = str(st.session_state.get(mode_key) or "view")
                _k_dn = f"ped_dn_{org_id}_{_puid}"
                _k_ro = f"ped_ro_{org_id}_{_puid}"
                _k_pw = f"ped_pw_{org_id}_{_puid}"
                _k_pw2 = f"ped_pw2_{org_id}_{_puid}"
                _rev_key = f"ped_uidrev_{org_id}_{_puid}"

                prof = get_user(_puid) or u_sel
                _cur_role = str(prof.get("role") or "")
                _cur_dn = str(prof.get("display_name") or "")
                _cur_em = str(prof.get("email") or "")
                _cur_oid = str(prof.get("org_id") or "")

                with st.expander("선택한 사용자 정보", expanded=True):
                    if _umode == "view":
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
.mgmu-sub { color: #94a3b8; font-size: 0.8rem; margin-top: 0.25rem; }
.mgmu-card { max-width: 640px; }
</style>
                            """,
                            unsafe_allow_html=True,
                        )
                        _blocks = [
                            (
                                "역할",
                                html.escape(_role_label_ko(_cur_role)),
                                html.escape(_cur_role),
                            ),
                            ("닉네임", html.escape(_cur_dn) if _cur_dn else "—", ""),
                            ("이메일", html.escape(_cur_em), ""),
                            ("기업 ID", html.escape(_cur_oid), ""),
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

                        def _mask_uid_full(u: str) -> str:
                            s = str(u)
                            if len(s) <= 8:
                                return "••••••••"
                            return f"{s[:4]} … {s[-4:]}"

                        _show_full = st.session_state.get(_rev_key, False)
                        u1, u2 = st.columns([4, 1])
                        with u1:
                            st.code(
                                _puid if _show_full else _mask_uid_full(_puid),
                                language=None,
                            )
                        with u2:
                            if not _show_full:
                                if st.button(
                                    "전체 보기",
                                    key=f"ped_show_{org_id}_{_puid}",
                                ):
                                    st.session_state[_rev_key] = True
                                    st.rerun()
                            else:
                                if st.button(
                                    "숨기기",
                                    key=f"ped_hide_{org_id}_{_puid}",
                                ):
                                    st.session_state[_rev_key] = False
                                    st.rerun()

                        if st.button(
                            "정보 변경",
                            key=f"ped_to_edit_{org_id}_{_puid}",
                            type="primary",
                            use_container_width=True,
                        ):
                            st.session_state[mode_key] = "edit"
                            if _k_dn not in st.session_state:
                                st.session_state[_k_dn] = _cur_dn
                            if _k_ro not in st.session_state:
                                st.session_state[_k_ro] = (
                                    _cur_role
                                    if _cur_role in _roles_edit
                                    else "Student"
                                )
                            st.rerun()
                    else:
                        st.caption(
                            "닉네임·역할·비밀번호를 수정할 수 있습니다. 비밀번호는 변경할 때만 입력하세요."
                        )
                        if _k_dn not in st.session_state:
                            st.session_state[_k_dn] = _cur_dn
                        if _k_ro not in st.session_state:
                            st.session_state[_k_ro] = (
                                _cur_role
                                if _cur_role in _roles_edit
                                else "Student"
                            )

                        with st.form(f"ped_form_{org_id}_{_puid}"):
                            st.text_input("닉네임", key=_k_dn)
                            st.selectbox("역할", _roles_edit, key=_k_ro)
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
                            _save_ed = st.form_submit_button("저장", type="primary")

                        if st.button(
                            "취소",
                            key=f"ped_cancel_{org_id}_{_puid}",
                            use_container_width=True,
                        ):
                            st.session_state[mode_key] = "view"
                            st.session_state.pop(_k_pw, None)
                            st.session_state.pop(_k_pw2, None)
                            st.rerun()

                        if _save_ed:
                            _dn_v = (st.session_state.get(_k_dn) or "").strip()
                            _role_v = st.session_state.get(_k_ro)
                            _pw1 = st.session_state.get(_k_pw) or ""
                            _pw2 = st.session_state.get(_k_pw2) or ""
                            _org = get_organization(org_id) or {}
                            _max_s = int(_org.get("max_slots") or 0)
                            _n_stu = count_students_in_org(org_id)
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
                                            _puid,
                                            display_name=_dn_v,
                                            role=str(_role_v),
                                        )
                                        update_auth_user(
                                            _puid,
                                            display_name=_dn_v,
                                            password=_pw1
                                            if (_pw1 and _pw1 == _pw2)
                                            else None,
                                        )
                                        st.session_state.pop(_k_pw, None)
                                        st.session_state.pop(_k_pw2, None)
                                        st.session_state[mode_key] = "view"
                                        st.success("저장했습니다.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(str(e))

                        st.divider()
                        st.caption(
                            "계정 삭제 시 Firebase 인증과 Firestore 사용자 문서가 함께 제거됩니다."
                        )
                        _op_uid = str(st.session_state.get(AUTH_UID) or "").strip()
                        if _puid == _op_uid:
                            st.warning("본인 계정은 삭제할 수 없습니다.")
                        else:
                            _del_key = f"ped_del_confirm_{org_id}_{_puid}"
                            if not st.session_state.get(_del_key):
                                if st.button(
                                    "계정 삭제",
                                    key=f"ped_del_{org_id}_{_puid}",
                                    type="primary",
                                ):
                                    st.session_state[_del_key] = True
                                    st.rerun()
                            else:
                                st.error("정말 이 계정을 삭제할까요?")
                                d1, d2 = st.columns(2)
                                if d1.button(
                                    "취소",
                                    key=f"ped_del_cancel_{org_id}_{_puid}",
                                ):
                                    st.session_state.pop(_del_key, None)
                                    st.rerun()
                                if d2.button(
                                    "삭제 확정",
                                    key=f"ped_del_ok_{org_id}_{_puid}",
                                ):
                                    try:
                                        delete_auth_user(_puid)
                                        delete_user_document(_puid)
                                        st.session_state.pop(_del_key, None)
                                        st.session_state.pop(mode_key, None)
                                        st.session_state.pop(_rev_key, None)
                                        for _k in (
                                            _k_dn,
                                            _k_ro,
                                            _k_pw,
                                            _k_pw2,
                                        ):
                                            st.session_state.pop(_k, None)
                                        _remain = [
                                            x
                                            for x in uids_ordered
                                            if x != _puid
                                        ]
                                        if _remain:
                                            st.session_state[
                                                f"people_detail_sel_{org_id}"
                                            ] = _remain[0]
                                        else:
                                            st.session_state.pop(
                                                f"people_detail_sel_{org_id}",
                                                None,
                                            )
                                        st.success("계정을 삭제했습니다.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(str(e))
