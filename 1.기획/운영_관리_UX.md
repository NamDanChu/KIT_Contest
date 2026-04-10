# EduChain AI — 운영자 흐름·관리 메뉴 UX

`EduChain_AI` 앱 기준으로 **멀티페이지 구성**, **회원가입·역할**, **관리(기업) 단위** 설계를 정리합니다. (문서 위치: `1.기획/`)

---

## 1. 화면·내비게이션 (현재 구현)

| 항목 | 내용 |
|------|------|
| **멀티페이지** | `EduChain_AI/pages/` — `1_Login`, `2_관리`, `3_Teacher`, `4_학생관리`, `5_Student`, 진입은 `Home.py` |
| **역할별 노출** | `services/sidebar_helpers.py`에서 로그인 시 **CSS**로 멀티페이지 링크 일부 숨김(예: 학생에게 `2_관리` 숨김). 역할·기업 미배정 시 Home만 강조 |
| **교사·학생 전용 메뉴** | 각각 `3_Teacher` / `5_Student` 페이지 **사이드바**에서 개요·수업 선택·탭 이동(`render_teacher_sidebar`, `render_student_sidebar`) |
| **4_학생관리** | 교사 플로우에서만 연결되도록 상단 네비에서 숨기는 처리(리다이렉트·전용 진입) |

---

## 2. 회원가입·역할 정책 (요약)

### 2.1 이메일 회원가입

- **운영자(Operator)** / **유저(User)** 선택 — 유저는 **학원명 없이** 가입 가능.  
- 유저는 **Home**에서 **초대 코드**로 소속 신청 → `JoinRequests` + 운영자 **승인** 후 `Teacher`/`Student` 반영.  
- **비밀번호 확인** 필드, 최소 길이 등은 `1_Login`·`auth_session`에서 검증.

### 2.2 첫 가입자·OAuth

- **첫 Firestore Users 문서가 없을 때** 이메일 가입: **Operator** 등 정책은 `auth_session.apply_firebase_rest_result` 등에 구현.  
- **Google 로그인**: 사용자 수·기본 조직(`DEFAULT_ORG_ID`) 등 규칙은 `auth_session.py`와 기획 일치.

(세부 필드명·예외는 `1.기획/EduChain_AI_전체정리.md` §3 및 코드를 본다.)

---

## 3. Firestore 필드 (요약)

### `Users`

`uid`, `email`, `role`, `org_id`, `display_name`, `membership_pending`, `pending_org_id` 등 — 승인 대기·초대 연동.

### `Organizations`

`org_id`, `org_name`, `max_slots`, `plan`, `owner_uid` 등.

---

## 4. 「관리」 메뉴 안에서의 흐름 (운영자)

1. **2_관리** 진입 — 기업 목록·추가·선택.  
2. 기업 선택 후 **세부 설정** — 사이드바 카테고리(기본 정보·플랜·교사·학생·콘텐츠·**AI 토큰 활용량** 등).  
3. **교사·학생** 탭 — 초대 코드, **가입 승인 대기**, 소속 사용자 목록·상세 편집.  
4. **콘텐츠** — 카테고리·교사 배치, 과목별 수업 통계(운영자 모드).

---

## 5. 세션 키 (참고)

`session_keys.py`에 정의 — 예: `AUTH_UID`, `AUTH_ROLE`, `AUTH_ORG_ID`, `MGMT_SELECTED_ORG_ID`, `MGMT_DETAIL_TAB`, 교사/학생용 `TEACHER_*`, `STUDENT_*` 등.

---

## 6. 관련 코드 위치

| 영역 | 경로 |
|------|------|
| 로그인·회원가입 | `EduChain_AI/pages/1_Login.py` |
| 관리 | `EduChain_AI/pages/2_관리.py`, `services/mgmt_*.py` |
| 사이드바·네비 CSS | `EduChain_AI/services/sidebar_helpers.py` |
| 역할·Firestore 동기화 | `EduChain_AI/services/auth_session.py` |
| CRUD | `EduChain_AI/services/firestore_repo.py` |

전체 아키텍처는 `1.기획/EduChain_AI_전체정리.md`, 개발 순서는 `1.기획/개발순서.md`와 함께 보면 된다.
