# EduChain AI — 운영자 흐름·관리 메뉴 UX

`EduChain_AI` 앱 기준으로, **사이드바 노출 범위**, **회원가입·역할**, **관리(기업) 단위** 설계를 정리합니다.

---

## 1. 화면·내비게이션 원칙

| 항목 | 내용 |
|------|------|
| **멀티페이지** | `pages/`에는 **로그인**(`1_Login`)과 **관리**(`2_관리`)만 둡니다. 교사·학생·운영자 전용 페이지는 제거하고, `views/`에 스텁만 두었습니다. |
| **확장 방향** | 교사·학생·콘텐츠 기능은 **관리 → 기업 선택 후** 같은 페이지 안의 탭·세션 상태로 넣거나, 추후 `pages/2_관리.py` 하위를 모듈로 분리합니다. |
| **Streamlit 제약** | 역할별로 사이드바 항목을 **숨기는** 것은 기본 제공이 아니므로, 학생이 `관리`를 누르면 안내 메시지로 막습니다. (필요 시 커스텀 컴포넌트·단일 `Home` 라우팅으로 전환 가능) |

---

## 2. 회원가입·역할 정책

### 2.1 이메일 회원가입

입력 필드:

- **이름** (`display_name` → Firestore `Users`)
- **학원 또는 학교(기업) 이름** — 첫 가입 시 생성되는 **Organizations** 문서의 `org_name`
- 이메일, 비밀번호

### 2.2 첫 가입자 = 운영자(Operator)

- Firestore `Users` 컬렉션에 **문서가 하나도 없을 때** 가입하는 계정은 **`Operator`**.
- 동시에 **Organizations**에 문서를 하나 만들고, `owner_uid`에 해당 사용자 UID를 넣습니다.
- **두 번째 사용자부터**는 기본 **`Student`** 역할, `org_id`는 `secrets`의 `DEFAULT_ORG_ID`(기본 조직)로 연결됩니다. (초대·조직 배정 로직은 추후 강화 가능)

### 2.3 Google 로그인

- 폼 없이 가입 시: 전체 사용자 수가 0이면 **Operator**만 두고 **기업 문서는 자동 생성하지 않음** (관리 화면에서 추가). 그 외에는 **Student** + `DEFAULT_ORG_ID`.

---

## 3. Firestore 필드 보강

### `Users`

| 필드 | 설명 |
|------|------|
| `uid`, `email`, `role`, `org_id` | 기존 |
| `display_name` | 표시 이름 |

### `Organizations`

| 필드 | 설명 |
|------|------|
| `org_id`, `org_name`, `max_slots`, `plan` | 기존 |
| `owner_uid` | 해당 기업을 등록한 운영자 UID (목록·권한 필터에 사용) |

---

## 4. 「관리」 메뉴 안에서의 흐름

1. **운영자**로 로그인한 뒤 **관리** 페이지 진입.
2. **내 학원·학교** 탭: `owner_uid == 본인` 인 기업 목록 표시 → **선택** 시 `session_state["mgmt_selected_org_id"]`에 저장.
3. **선택한 기업 · 세부 관리** 영역: 플랜·슬롯 등 요약 표시.  
   → 이후 **교사·학생·콘텐츠·통계** 등은 이 블록 안에 단계적으로 추가.
4. **기업 추가** 탭: 같은 운영자가 **여러 학원·학교(기업)** 를 추가 등록 가능 (`create_organization`).

---

## 5. 세션 키 (참고)

| 키 | 용도 |
|----|------|
| `auth_display_name`, `auth_org_name` | 헤더·사이드바 표시 |
| `mgmt_selected_org_id` | 관리 화면에서 선택한 기업 |

---

## 6. 관련 코드 위치

- 로그인·회원가입: `EduChain_AI/pages/1_Login.py`
- 관리: `EduChain_AI/pages/2_관리.py`
- 역할·Firestore 동기화: `EduChain_AI/services/auth_session.py`
- CRUD: `EduChain_AI/services/firestore_repo.py`

전체 아키텍처는 `기획/EduChain_AI_전체정리.md`, 개발 순서는 `기획/개발순서.md`와 함께 보면 됩니다.
