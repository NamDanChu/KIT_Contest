# EduChain AI — GitHub 반영용 변경 요약

커밋 메시지·PR 본문에 붙여 쓸 수 있도록 **최근 작업**을 요약했다. (과거: AI 토큰 미터링 중심 → 이후 성능·차트·문서 경로 정리 포함)

---

## 한 줄 요약 (최신 권장)

Gemini 호출 **입·출력 토큰**을 Firestore에 누적하고, 교사·운영 화면에서 **용도·세부 기능·사용자별**로 확인·검색하는 **「AI 토큰 활용량」**; 배포 **성능**(Firestore `array_contains`, `st.cache_data`, 사이드바·본문 중복 제거, Home 세션 스로틀) 및 Matplotlib **번들 한글 폰트**; 기획 문서는 **`1.기획/`** 폴더에 정리.

---

## 배경 (AI 토큰)

- 교육 SaaS에서 **AI 변동비**를 설명·관리하려면 “누가·어떤 기능에·얼마나” 썼는지가 필요하다.
- 기존에는 집계 없이 Gemini만 호출했으므로, **관측 가능한 미터링** 단계를 코드에 반영했다.

---

## 주요 변경 사항 (AI 토큰)

### 1. Firestore

| 경로 | 역할 |
|------|------|
| `Organizations/{org_id}/AiTokenRollup/{category_id \| __org__}` | 버킷별·세부 기능(`kind_*`) **토큰·호출 수 누적** |
| `Organizations/{org_id}/AiTokenEvents/{id}` | 호출 **1건 로그** — `usage_kind`, `bucket`, 토큰, `actor_uid` / 역할 / 표시명, `category_id` |

### 2. 백엔드

- **`services/gemini_client.py`**: `_generate` 성공 시 응답 `usage_metadata`에서 토큰 추출 후 누적·이벤트 기록. 각 공개 함수에 `usage` dict (`org_id`, `category_id`, `bucket`, `usage_kind`) 전달.
- **`services/firestore_repo.py`**: `increment_ai_token_rollup`, `append_ai_token_event`, 집계·이벤트 목록 조회, 수업 목록 `array_contains`·캐시 무효화 등.
- **호출부 연동**: `lesson_mgmt_ui`, `student_portal`, `student_quiz_mix`, `course_stats_ui`, `3_Teacher` 등에서 `usage`·`usage_kind` 지정.

### 3. UI

- **교사** (`pages/3_Teacher.py`): 사이드바 **「AI 토큰 활용량」** — 선택 수업만, 용도/세부 기능/사용자별/최근 호출, **사용자 검색**.
- **운영** (`pages/2_관리.py` + `sidebar_helpers`): 기업 상세 **「AI 토큰 활용량」** 탭 — 기업 전체·수업별·사용자별·최근 호출, 동일 검색.
- **`services/ai_usage_ui.py`**: 표·차트·검색·필터. 차트는 **matplotlib** 가로 막대; **배포 Linux**에서 한글 깨짐 방지를 위해 **`assets/fonts/NanumGothic-Regular.ttf`** 를 `addfont`로 등록. `matplotlib` 미설치 시 **`st.bar_chart` 폴백**.
- **수업 통계(교사)**: 상세 AI 토큰 블록은 제거하고 **AI 토큰 메뉴** 안내. **운영자·과목 통계** 화면에서는 기존처럼 상단에 AI 요약 유지.

### 4. 의존성

- **`requirements.txt`**: `matplotlib>=3.8.0`; 미사용 **chromadb** 제거(스텁만 유지 시).

---

## 성능·배포 (2026-04 요약)

- 수업 목록: **`array_contains`**, **`@st.cache_data`**, 사이드바에 **categories/courses 전달**로 중복 조회 제거.
- Home: **`refresh_session_from_firestore`** 스로틀.
- 기획 문서 폴더명 **`1.기획/`**, AI 협업 색인 **`AI_협업_자료/`** 정리.

---

## 관련 파일 (참고)

```
EduChain_AI/services/gemini_client.py
EduChain_AI/services/firestore_repo.py
EduChain_AI/services/ai_usage_ui.py
EduChain_AI/services/lesson_mgmt_ui.py
EduChain_AI/services/student_portal.py
EduChain_AI/services/student_quiz_mix.py
EduChain_AI/services/course_stats_ui.py
EduChain_AI/services/sidebar_helpers.py
EduChain_AI/pages/3_Teacher.py
EduChain_AI/pages/2_관리.py
EduChain_AI/requirements.txt
EduChain_AI/assets/fonts/NanumGothic-Regular.ttf
1.기획/EduChain_AI_전체정리.md
1.기획/진행중상황.md
AI_협업_자료/README.md
```

---

## 커밋 메시지 예시

```
feat(ai): Gemini 토큰 누적·이벤트 로그 및 AI 토큰 활용량 UI(교사/운영)

- Firestore AiTokenRollup / AiTokenEvents
- usage_kind·actor 세션 기록, 사용자 검색·가로 막대 차트
- matplotlib·번들 한글 폰트; perf: array_contains·cache·sidebar dedupe
```

---

## 제한·메모

- **과금·청구**와 직접 연동하지 않음 — **관측·운영 투명성** 목적.
- 구버전 호출·actor 미기록 이벤트는 “미기록”으로 표시될 수 있음.
- 이벤트 목록은 **최근 N건** 범위에서 사용자별 합산(문서에 명시된 상한 참고).
