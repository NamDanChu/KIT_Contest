# EduChain AI — 전체 기획 정리

> **문서 위치:** 저장소 루트의 `1.기획/` 폴더. (구 `기획/` 폴더명을 정리한 경우 링크는 `1.기획/` 기준으로 통일.)

원문: `정리폴더/기본정리.md`를 바탕으로 **해야 할 순서**, **단계별로 쌓이는 시스템**, **구축 대상 시스템**, **파일 구조·메커니즘**을 한곳에 모았습니다.

**AI 협업·제출용 색인:** `AI_협업_자료/README.md` — 기획 문서 읽는 순서·협업 프로세스·구현 이력 요약.

---

## 1. 프로젝트 한 줄 요약

| 항목 | 내용 |
|------|------|
| 이름 | **EduChain AI** |
| 슬로건 | AI 에이전트와 실시간 클라우드가 결합된 초개인화 학습 생태계 |
| 인프라 핵심 | **Firebase** (Auth + Firestore) — 보안·실시간 데이터 |
| 목표 톤 | 상용화 직전 수준의 **교육 SaaS** 제안 |

**핵심 가치**

1. **신뢰성** — 기업(조직)별 데이터 격리 + Firebase 인증  
2. **효율성** — 교사 업무 자동화, 학생 즉시 피드백  
3. **지속 가능성** — 슬롯 기반 요금제로 수익 구조 명확화  

---

## 2. 기술 스택과 역할

| 구분 | 기술 | 역할 |
|------|------|------|
| UI / App | **Streamlit** | 메인 웹·앱 화면 |
| 인증 | **Firebase Auth** | 이메일·비밀번호 가입/로그인 |
| DB | **Cloud Firestore** | 조직·역할·학습·채팅 이력 실시간 저장 |
| AI | **Gemini**(Flash 등) | 수업 요약·퀴즈·통계 분석·학생 질문/코칭 등 |
| 벡터 검색 | **ChromaDB(선택·기획)** | `rag_pipeline.py`는 스텁; `requirements.txt`에서 미사용 **chromadb 의존성 제거**(배포 부담 감소). 향후 RAG 본구현 시 재도입·외부 벡터 DB 검토 |
| 배포 | **Streamlit Cloud** 등 | GitHub 연동 라이브 URL |

**데이터·처리 흐름(개념)**

- **로그인** → Firebase Auth 발급 `uid` → Firestore에서 `role`, `org_id` 조회 → 역할별 화면 분기  
- **교사** → PDF 업로드 → 텍스트 추출·청킹 → ChromaDB 저장 → Gemini로 키워드·퀴즈 생성  
- **학생** → 질문 → ChromaDB로 관련 교안 검색 → Gemini가 인용·설명 → `ChatLogs`에 기록  
- **운영자** → Firestore의 조직·사용자 수와 `max_slots` 비교 → 대시보드·슬롯 시연  

---

## 3. Firestore 데이터 모델

### `Organizations`

| 필드 | 설명 |
|------|------|
| `org_id` | 기업 코드 (PK) |
| `org_name` | 기업/학원명 |
| `max_slots` | 구매 학생 슬롯 수 |
| `plan` | 요금제 (Starter / Pro / Enterprise 등) |
| `owner_uid` | 기업을 등록한 운영자 UID (관리 화면에서 목록 필터) |

### `Users`

| 필드 | 설명 |
|------|------|
| `uid` | Firebase Auth UID (PK) |
| `email` | 이메일 |
| `display_name` | 표시 이름 |
| `role` | `Teacher` / `Student` / `Operator` / `User`(소속 전·초대 승인 대기 등) |
| `org_id` | 소속 조직 (FK, 없을 수 있음) |
| `membership_pending` 등 | 초대 소속 **승인 대기** 시 플래그·`pending_org_id`·`pending_role`(선택) |

### `ChatLogs`

| 필드 | 설명 |
|------|------|
| `log_id` | 기록 ID |
| `uid` | 학생 ID |
| `query` / `answer` | 질문·답변 |
| `timestamp` | 시각 |

**격리 원칙(발표용 포인트)**  
쿼리·보안 규칙에서 **`org_id`(및 필요 시 `uid`)** 기준으로 데이터가 섞이지 않게 설계한다는 메시지와 맞추면 됨.

### 3.1 확장 — 콘텐츠 카테고리·주차·학습 기록 (현재 코드 기준)

| 경로 | 설명 |
|------|------|
| `Organizations/{org_id}/ContentCategories/{category_id}` | 수업(카테고리). `teacher_uids`, `student_uids`, `name`, `description`, `teacher_overview`, **`operator_feedback_teacher`**, **`operator_feedback_student`**(운영자→교사/학생 메모) 등 |
| `.../ContentCategories/{category_id}/LessonWeeks/{week_doc_id}` | 주차별 수업 설계. `week_index`, `title`, `learning_goals`, `lesson_video_url`, `live_session_active`, 공개·기간(`access_mode`, `window_*`) 등 |
| `Users/{uid}/LessonProgress/{doc_id}` | 학생·수업·주차별 **시청 진행률** `progress_percent`(0~100), 영상 재생 위치 **`last_video_position_sec`**, **`video_duration_sec`**(클라이언트 주기 저장). **퀴즈(마지막 제출 스냅샷)**: `quiz_correct` / `quiz_total`, `quiz_passed`, **`quiz_attempt_count`**(제출할 때마다 +1), **`quiz_wrong_indices`**(0-based 오답 문항 인덱스), `quiz_wrong_count`. `doc_id`는 org+category+week 해시 규칙 |
| `.../ContentCategories/{category_id}/StudentLessonQuestions/{doc_id}` | 해당 수업에서 학생 **AI 채팅 질문·답변** 로그. `question`, `answer`, `week_doc_id`, `week_title`, **`video_position_sec`**, **`video_position_label`** 등(질문 시점 영상 위치) |
| `.../ContentCategories/{category_id}/StudentIntegratedQuizLogs/{doc_id}` | **통합 퀴즈**(연습) 활동 로그 — 일괄 채점·무한 연습 정답 확인·세션 종료 등(교사 코칭용) |
| `Organizations/{org_id}/JoinRequests/{uid}` | 초대 코드 **소속 신청** 승인 대기(운영자 승인 후 `Users` 역할·소속 반영) |
| `Organizations/{org_id}/AiTokenRollup/{category_id \| __org__}` | **Gemini 토큰 누적** — 용도 **버킷**별(`teacher_lesson`, `student_chat` 등) `*_prompt` / `*_completion` / `*_calls`, 세부 기능별 `kind_{usage_kind}_*` 필드(merge + increment) |
| `Organizations/{org_id}/AiTokenEvents/{event_id}` | **호출 1건 로그** — `usage_kind`, `bucket`, 토큰 수, `actor_uid` / `actor_role` / `actor_display_name`(로그인 사용자), `category_id`, 시각 등 |

**기타**  
- `ChatLogs` — 범용 채팅 로그(초기 설계). 학생 수강 AI는 위 `StudentLessonQuestions`에 **수업·주차 맥락**을 붙여 저장하는 쪽으로 보강됨.

---

## 4. 역할별 화면·기능

| 역할 | 핵심 기능 | UI 요약 |
|------|-----------|---------|
| **공통** | 이메일/비밀번호 로그인 | 로그인 후 Firestore `role`로 대시보드 이동 |
| **Teacher** | PDF 업로드 → 키워드·객관식 퀴즈 자동 생성 | 업로드 + 퀴즈 미리보기·편집 |
| **Student** | 교안 기반 RAG Q&A (페이지·맥락 인용) | 좌: 자료 / 우: 챗봇 |
| **Operator** | 가입 학생 수 vs `max_slots`, 질문 빈도 등 | 지표 카드 + 그래프, 슬롯 확장 시연 |

**운영자 전용 내비·기업 관리 UX** (사이드바는 로그인·관리 중심, 기업 선택 후 세부 기능): `1.기획/운영_관리_UX.md`

### 4.1 현재 앱 구조 (실행 코드: `EduChain_AI/`)

| 페이지 / 모듈 | 역할 요약 |
|---------------|-----------|
| `Home.py` | 진입, 멀티페이지 네비, 로그인 시 사용자 블록 |
| `pages/1_Login.py` | 이메일·Google·초대 가입·**운영자/유저 회원가입**·비밀번호 확인·가입 후 승인 흐름 안내 |
| `pages/2_관리.py` | 운영자: 기업·플랜·슬롯·사용자·콘텐츠 카테고리·교사 배치 — 기업 상세 사이드바 **AI 토큰 활용량** 탭(전사·수업별·사용자별·최근 호출) |
| `pages/3_Teacher.py` | 교사: 수업 선택 후 **개요** / **학생 관리** / **수업 통계** / **AI 토큰 활용량** / **수업 관리**(주차·영상·AI·질문 로그 등) |
| `pages/4_학생관리.py` | (교사 전용 플로우 연결용) 학생 관리 보조 |
| `pages/5_Student.py` | 학생: **개요** → 수업 선택 → **수업 개요** / **수업 수강**(주차 목록·영상 플레이어·우측 패널) |
| `services/student_portal.py` | 학생 개요·주차 목록·수강 플레이어(YouTube/Vimeo/HTML5, 진행률 저장, 우측 AI/라이브/개요) |
| `services/sidebar_helpers.py` | 교사/학생 사이드바, `st.fragment` 복구 CSS 등 |
| `services/lesson_mgmt_ui.py` | 교사 수업 관리 패널(주차 CRUD, 영상 URL, 라이브 토글 등) |
| `services/course_stats_ui.py` | **수업 통계**(교사·운영자 공통): 수강 인원, 주차 카드·상세(해당 주차 **퀴즈 응시·제출·오답 합·문항별 오답 빈도**), 질문 요약, **전체 퀴즈 집계**(응시 횟수 합·제출 건수·오답 문항 수 합), Gemini **수업 전반 분석**(`quiz_block`에 집계 반영), 운영자 모드 시 피드백·**AI 교사 피드백 초안** |
| `services/mgmt_content.py` | 운영자 콘텐츠: 카테고리·교사 배치(설명·하위 JSON 필드는 UI에서 제거, DB 기존값 유지) |
| `services/mgmt_people.py` | 교사·학생: 초대 코드·**가입 승인 대기**·계정 생성·**소속 사용자 목록**(검색·정렬·표 선택→상세·편집·삭제) |
| `services/student_quiz_mix.py` | **통합 퀴즈**(일괄/무한), AI 코칭 버튼, Firestore 로그 append |
| `services/auth_session.py` | 로그인 후 프로필 동기화·초대 승인 대기·`User` Home 초대 신청 등 |
| `services/gemini_client.py` | 수업 통계 분석(`analyze_course_statistics`, `quiz_block`), **학습 프로필 분석**(`analyze_student_learning_profile` — **퀴즈 요약 `quiz_summary_block`** 포함), 운영자 피드백 초안, 주차 맥락 질문 답변(`answer_student_lesson_question`) 등 — 성공 시 **`usage_metadata` 토큰**을 읽어 Firestore **누적·이벤트** 기록(`usage` dict: `org_id`, `category_id`, `bucket`, `usage_kind`) |
| `services/ai_usage_ui.py` | **AI 토큰 활용량** UI — 용도/세부 기능/수업별 표·**matplotlib 가로 막대** 차트(미설치 시 `st.bar_chart` 폴백), **사용자 검색**, 교사·운영 공통 패널 |
| `services/firestore_repo.py` | `increment_ai_token_rollup`, `append_ai_token_event`, `aggregate_ai_usage_*`, `list_recent_ai_token_events` 등 |

**학생 수강 UX 요약**  
- 사이드바: 개요, 수업 선택(selectbox), 수업 개요 / 수업 수강.  
- **수업 수강**에서 주차 선택 시 전체폭 플레이어: 왼쪽 영상(`components.html` + Firebase로 진행률), 오른쪽 라이브·AI 채팅·주차 개요.  
- **Streamlit `st.fragment`(≥1.33)** 으로 우측만 갱신해 영상 iframe 재마운트를 줄임; 우측 패널 접기 시 CSS로 열 비율 조정.  
- 저장된 `progress_percent`로 재생 시작 위치 근처 **seek**(YouTube/Vimeo/HTML5).  
- AI 질문은 Firestore `StudentLessonQuestions`에 저장 → 교사 **개요** 탭에서 **학생 AI 질문** 목록으로 확인. 질문 시점 **영상 위치**(초·라벨) 저장 가능.
- **교사** **수업 통계**·**학생 관리**(정보 보기): 주차별 완료·질문·**퀴즈(응시·오답·틀린 문항 지문)**·Gemini 분석(**학생 분석에 퀴즈 요약 반영**); 분석 결과는 **expander**로 접기. **AI 토큰 활용량** 전용 메뉴에서 선택 수업 기준 토큰·세부 기능·**사용자별**·최근 호출(검색 가능).
- **운영자** **콘텐츠·통계**: 과목별로 교사와 동일한 통계·운영자→교사/학생 피드백·AI 초안; **학생 수업 개요**에 운영자 공지 표시. **관리 → 기업 → AI 토큰 활용량** 에서 기업 전체·수업별·**사용자별**·최근 호출(검색 가능).

---

## 5. 요금제(비즈니스 모델)

| 플랜 | 월 가격 | 학생 슬롯 | 주요 기능 |
|------|---------|-----------|-----------|
| Starter | 무료 체험 | 5명 | 기본 RAG 채팅(텍스트) |
| Pro | ₩190,000 | 50명 | PDF 분석, AI 퀴즈, 질문 통계 |
| Premium | ₩450,000 | 150명 | 영상 자막 분석(확장), 지원, 슬롯 확장 |

**코드 연동:** `Organizations.max_slots`, `plan` — `services/plan_limits.py` 등과 연계. 현재는 **좌석(학생 수)** 중심이다.

### 5.1 비즈니스 모델 확장 방향 (학생 수 외 — 기획 메모)

학생 수만 과금하면 **AI API 변동비**(Gemini 호출 횟수·토큰·모델 단가 차이)를 가격에 반영하기 어렵다. 아래를 **과금 축** 후보로 두고, 우선순위·측정 가능 여부·고객 설명 난이도 순으로 검토하는 것을 권장한다.

| 축 | 설명 | 구현·운영 시 유의점 |
|----|------|---------------------|
| **좌석(학생 슬롯)** | 기존 — 조직이 동시에 둘 학생 계정 상한 | 이미 `max_slots`·승인 시 학생 수 집계와 연동 |
| **AI 사용량(량·가중치)** | 월·일 단위 **호출 수**, 또는 **추정 토큰**(입력+출력) 합 | 기능별 가중치 예: 주차 채팅 1, 퀴즈 생성 3, 수업 통계 분석 5, 통합 퀴즈 코칭 1 등. Firestore `UsageDaily/{orgId_YYYYMM}` 또는 `Organizations/{org}/Usage/{period}` 누적 |
| **모델 티어** | 기본 **Flash** vs 옵션 **Pro**(또는 최신 고가 모델) | `Organizations.ai_model_tier` 또는 플랜별 기본값; `gemini_client`에서 모델명 분기 |
| **공정 사용·상한** | 플랜별 **월 AI 크레딧**(포인트) 또는 **소프트 캡** 초과 시 알림·제한 | 초과 시: 기능 비활성 / 업셀 안내 / 익월 리셋 명시 |
| **투명성** | 운영자 화면에 **“이번 달 추정 사용량·남은 한도”** | Stripe 등 **정액+초과 종량**과 조합 가능 |

**권장 순서 (제품·엔지니어링)**

1. **관측**: Gemini 호출 지점마다 `org_id`·`feature`(enum)·`input_chars`/`approx_tokens`·`model_id`를 구조화 로그(또는 Firestore append + 일 배치 집계).  
2. **내부 원가 추정**: Google AI Studio·청구서 기준으로 **건당·토큰당** 대략 단가 표를 만들고, 플랜별 마진 목표와 맞춰 **포인트 환산** 또는 **포함 토큰** 설계.  
3. **가격·패키지**: “학생 N명 + 월 AI 크레딤 M” **번들**로 팔지, 좌석과 크레딧을 **분리 과금**할지 결정.  
4. **강제 순서**: 알림(80%/100%) → 읽기 전용 → 유료 업셀 (학습 연속성을 해치지 않는 순으로).

**관련 코드 앵커:** `services/gemini_client.py`의 `_generate` 및 `_record_gemini_usage` — 성공 응답의 **`usage_metadata`** 로 입력·출력 토큰을 읽고, `firestore_repo.increment_ai_token_rollup` / `append_ai_token_event`에 전달한다. 기능별 태그는 `usage_kind`(예: `lesson_quiz_json`, `student_week_ai_chat`)로 통일.

---

## 5.2 성능·배포 최적화 (2026-04, 코드 반영)

배포 후 **렉·Firestore 읽기 과다** 완화를 위해 아래를 적용했다.

| 항목 | 내용 |
|------|------|
| **수업 목록 조회** | `list_content_categories_for_teacher` / `for_student`: 기존 **전체 카테고리 스트림 + 파이썬 필터** → Firestore **`array_contains`** 단일 쿼리(`teacher_uids` / `student_uids`). |
| **캐시** | 동일 함수에 **`@st.cache_data(ttl=45)`** — 짧은 시간 내·동일 rerun 중복 호출 완화. 카테고리 **생성·수정·삭제** 시 `invalidate_teacher_student_category_caches()`로 무효화. |
| **중복 제거** | 교사·학생 페이지에서 사이드바와 본문이 같은 목록을 두 번 읽지 않도록 **`render_teacher_sidebar(categories=...)`**, **`render_student_sidebar(courses=...)`** 로 한 번 조회 결과를 공유. |
| **Home 프로필 동기화** | `refresh_session_from_firestore()` — rerun마다 Firestore를 치지 않도록 **최소 간격(약 20초)** 스로틀. 승인 직후 즉시 반영이 필요하면 브라우저 새로고침. |
| **의존성** | 미사용 **chromadb** 제거(콜드 스타트·설치 시간 감소). |

**한계(구조):** Streamlit은 **위젯 상호작용마다 스크립트 전체 rerun** + WebSocket 동기화이므로, “앱 반응이 무거운 느낌”은 완전히 없애기 어렵다. 위 조치는 **네트워크·Firestore 왕복**을 줄이는 방향이다.

---

## 5.3 차트 한글 폰트 (배포 환경 Linux)

**증상:** 로컬(Windows)에서는 정상인데, 배포 서버에는 **맑은 고딕·나눔** 등이 없어 Matplotlib 축·범례 한글이 **□(tofu)** 로 깨짐.

**대응:** `EduChain_AI/assets/fonts/NanumGothic-Regular.ttf`(OFL)를 저장소에 포함하고, `services/ai_usage_ui.py`의 `_configure_matplotlib_korean()`에서 **`fontManager.addfont()`** 로 등록 후 `rcParams`에 반영. 시스템 폰트 유무와 무관하게 **AI 토큰 활용량** 등 matplotlib 차트에서 한글이 나오도록 함.

---

## 6. 해야 할 일 — 권장 순서(로드맵)

원문 **일주일 완성** 일정을 **의존 관계**가 보이도록 재정렬했습니다.

| 순서 | 기간 | 해야 할 일 | 이 단계에서 “완성되는 것” |
|------|------|------------|---------------------------|
| **1** | 1~2일차 | Firebase 프로젝트 생성, Auth·Firestore 활성화, 규칙 초안 | 클라우드 백엔드(인증·DB) 존재 |
| **2** | 1~2일차 | Streamlit + `firebase-admin`(또는 클라이언트 SDK)로 로그인·회원가입, 로그인 후 `Users` 읽기 | **게이트웨이**: 로그인 → 역할 분기 |
| **3** | 3~4일차 | Gemini API 연동, PDF 파이프라인, ChromaDB 저장·검색 | **AI 코어**: RAG 파이프라인 |
| **4** | 3~4일차 | Teacher: 업로드·퀴즈 생성 UI / Student: 분할 화면 채팅 + `ChatLogs` 저장 | **교사·학생 MVP** |
| **5** | 5일차 | Operator: `Organizations`·`Users` 집계, 슬롯 vs 현재 인원, 통계 UI | **운영 대시보드** |
| **6** | 6일차 | Streamlit 테마·CSS, 에러 처리, GitHub 푸시, Streamlit Cloud 배포 | **배포 가능한 데모** |
| **7** | 7일차 | 기술·비즈니스 문서, 시연 영상, 제출물 점검 | **제출 패키지** |

**의존 관계 요약**  
인프라(1) → 인증·역할(2) → RAG(3) → 역할별 UI·로그(4~5) → 광택·배포(6) → 문서·시연(7).

---

## 7. “구축되는 시스템” vs “앞으로 구축할 시스템”

### 이미 원문에서 “갖춘다”고 정의된 구성 요소

- **Firebase 프로젝트**: Auth + Firestore  
- **Streamlit 앱**: 단일 진입점 UI  
- **Gemini + ChromaDB**: 검색 증강 생성(RAG)  
- **Streamlit Cloud**: 공개 URL  

### 실제 구현 시 반드시 만들어야 하는 것(체크리스트)

세부 구현·검증 순서는 `1.기획/개발순서.md`와 맞춥니다.

- [x] Firestore 컬렉션·필드 생성 및 **보안 규칙**(조직/역할 기준 읽기·쓰기)  
- [x] 가입 시 `Users` 문서 생성, `org_id`·`role` 연결 로직  
- [x] Teacher: PDF → 청크 → 임베딩 → ChromaDB, 퀴즈 생성 프롬프트  
- [x] Student: 질의 → 벡터 검색 → 컨텍스트 + Gemini 답변, `ChatLogs` append  
- [x] Operator: 집계 쿼리(또는 Cloud Function) + 슬롯 시연(데모면 Firestore 필드 업데이트로도 가능)  
- [x] 환경 변수: Firebase 키, Gemini API 키, Chroma 저장 경로(클라우드에서는 영속 볼륨 또는 제약 안내)  

**※** 위 항목은 **기획·설계 관점에서의 완료**로 표시했습니다. **실제 코드 진행도**는 `1.기획/개발순서.md`·`1.기획/진행중상황.md`를 따릅니다. RAG·Chroma **전역 파이프라인**은 스텁에 가깝고, 수강·수업 AI는 **Gemini + 주차 맥락** 중심이다.

---

## 8. 파일 구조·메커니즘(권장안)

원문에 폴더 명세는 없으므로, **Streamlit + Firebase + RAG** 조합에 흔히 쓰는 구조를 제안합니다. 프로젝트 생성 후 실제 파일명은 팀에 맞게 조정하면 됩니다.

```
KIT_Contest/
├── 1.기획/
│   ├── EduChain_AI_전체정리.md    # 본 문서
│   ├── 진행중상황.md              # 구현 진행·다음 작업
│   ├── 연동필요.md, 개발순서.md, …
├── AI_협업_자료/                   # 공모전: AI 협업 방식·문서 색인
├── 정리폴더/                       # 초기 기획 원안
├── EduChain_AI/                    # 실제 Streamlit 앱 루트
│   ├── Home.py
│   ├── pages/
│   │   ├── 1_Login.py
│   │   ├── 2_관리.py
│   │   ├── 3_Teacher.py
│   │   ├── 4_학생관리.py
│   │   └── 5_Student.py
│   ├── services/
│   │   ├── firebase_app.py, auth_session.py, firestore_repo.py
│   │   ├── student_portal.py, lesson_mgmt_ui.py, lesson_access.py
│   │   ├── sidebar_helpers.py, gemini_client.py, rag_pipeline.py
│   │   ├── session_keys.py, plan_limits.py, …
│   ├── views/                      # placeholder 등 보조
│   ├── .streamlit/secrets.toml
│   └── requirements.txt            # streamlit>=1.33 권장(fragment)
├── chroma_data/                    # 로컬 Chroma (gitignore 권장)
└── …
```

### 메커니즘 요약

| 메커니즘 | 설명 |
|----------|------|
| **세션** | Streamlit `st.session_state`에 로그인 상태·`uid`·`role`·`org_id` 유지 |
| **라우팅** | 로그인 전후로 페이지 분기 또는 `st.navigation` / 멀티페이지 |
| **RAG** | 업로드 PDF → 텍스트 추출 → 청크 → 임베딩 → Chroma `collection`에 `org_id`·`doc_id` 메타데이터 부여 → 검색 시 동일 조직만 필터 |
| **감사 로그** | Student 채팅마다 `ChatLogs`에 비동기/동기 기록(데모는 동기로 단순화 가능) |
| **배포** | Streamlit Cloud는 **파일 시스템이 비영속**일 수 있음 → Chroma를 클라우드에 두려면 별도 스토리지 전략 또는 “데모는 소규모·재업로드”로 한정하는 식으로 정리 |

---

## 9. Streamlit UI 세팅 가이드

EduChain AI는 **Streamlit**이 단일 UI 프레임워크이므로, 아래 순서로 세팅하면 역할별 화면(로그인·교사·학생·운영자)을 일관되게 유지하기 좋습니다.

### 9.1 디렉터리·실행 진입점

| 항목 | 권장 |
|------|------|
| 실행 | `EduChain_AI` 폴더에서 `streamlit run Home.py` (저장소 루트가 아니라 **앱 루트** 기준) |
| 멀티페이지 | `pages/` — `1_Login`, `2_관리`, `3_Teacher`, `4_학생관리`, `5_Student` 등, 파일명 앞 숫자가 **사이드바 순서** |
| `set_page_config` | `Home.py`·`5_Student.py` 등 페이지별 호출 가능(Streamlit 멀티페이지 패턴). 공통 모듈 import 시 **첫 Streamlit 명령 전에 config가 오지 않게** 주의 |

**주의:** `set_page_config`는 앱의 **첫 Streamlit 명령**이어야 하므로, 공통 레이아웃 모듈을 만들 때도 “import 시점에 `st.write`가 먼저 도는” 구조는 피합니다.

### 9.2 `.streamlit/config.toml` (테마·동작)

프로젝트 루트에 `.streamlit/config.toml`을 두고 **브랜드 톤·폰트·사이드바**를 맞춥니다.

```toml
[theme]
primaryColor = "#1f77b4"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
font = "sans serif"

[server]
headless = true
enableCORS = false
enableXsrfProtection = true

[browser]
gatherUsageStats = false
```

- **배포(Streamlit Cloud)** 에서도 같은 파일이 적용됩니다.  
- **다크 모드** 등은 `[theme]`만 바꿔 재사용하면 됩니다.

### 9.3 비밀·키: `secrets.toml`

로컬 전용 `.streamlit/secrets.toml` ( **Git에 커밋하지 않음** — `.gitignore` 필수 ):

- `FIREBASE_...` / 서비스 계정 JSON 경로  
- `GEMINI_API_KEY`  
- 필요 시 Chroma 경로  

배포 시에는 Streamlit Cloud **Secrets** UI에 동일 키를 등록합니다. 앱에서는 `st.secrets["GEMINI_API_KEY"]`처럼 읽습니다.

### 9.4 화면 구조(역할별 UX와 맞추기)

| 역할 | UI 패턴 | Streamlit 요소 |
|------|---------|----------------|
| 공통 | 로그인 전에는 민감 페이지 비표시 또는 리다이렉트 | `st.session_state`에 `user`, `role`, `org_id` 존재 여부 검사 |
| Teacher | 업로드 + 결과 미리보기 | `st.file_uploader`, `st.tabs` 또는 `st.expander`로 “생성 / 편집” 분리 |
| Student | 좌·우 분할 | `left, right = st.columns([1, 1])` — 왼쪽 `st.pdf` 또는 텍스트, 오른쪽 채팅 `st.chat_message` |
| Operator | 지표 + 그래프 | `st.metric`, `st.columns`, `st.line_chart` / `plotly` 등 |

**세션 키 네이밍 예:** `auth_uid`, `auth_role`, `auth_org_id`, `chat_messages`(학생 채팅 히스토리). 한 파일에서 문자열을 흩뿌리지 말고 **상수 모듈**(`constants.py` 또는 `session_keys.py`)에 모으면 응집도가 올라갑니다.

### 9.5 스타일(CSS)·에러 메시지

- **테마만으로 부족할 때:** `st.markdown(..., unsafe_allow_html=True)`로 좁은 범위만 커스텀하거나, Streamlit 버전이 허용하면 **부트스트랩 수준의 거대 CSS**는 지양(유지보수·보안 이슈).  
- **에러:** 사용자에게는 짧은 한글 메시지, 로그/디버그는 `st.exception`은 개발용으로만.

### 9.6 배포 시 UI 관련 제약

- **ChromaDB 로컬 경로**는 클라우드에서 비어질 수 있음 → 시연용은 “세션당 재업로드” 문구를 UI에 넣거나, 운영자 페이지에 **저장소 상태**를 표시하는 편이 안전합니다.

---

## 10. Python 구조와 SOLID — 응집도↑, 결합도↓

현재 저장소에 `.py`가 없어도, **앞으로 코드가 생길 때** 아래를 기준으로 두면 교체·테스트·역할 추가가 쉬워집니다. Streamlit은 **스크립트가 위에서 아래로 재실행**된다는 점만 전제에 둡니다.

### 10.1 SOLID를 EduChain에 대응시키기

| 원칙 | 의미 | 이 프로젝트에서의 실천 |
|------|------|------------------------|
| **S** 단일 책임 | 한 모듈은 한 가지 변경 이유만 갖는다 | `pages/*.py`는 **화면 그리기·입력 수집**만. PDF 파싱·Firestore·Gemini 호출은 `services/`로 이동 |
| **O** 개방-폐쇄 | 확장에는 열려 있고, 수정에는 닫혀 있다 | 새 역할 페이지를 추가할 때 기존 `RAG` 코드를 고치지 않도록 **인터페이스 뒤**에 두기(아래 DIP) |
| **L** 리스코프 치환 | 상위 타입 자리에 하위 구현을 넣어도 동작이 깨지지 않게 | `AuthPort` 구현체를 Firebase용으로 두었다가 나중에 다른 IdP로 바꿔도 **같은 메서드 계약** 유지 |
| **I** 인터페이스 분리 | 쓰지 않는 메서드를 강요하지 않는다 | “거대한 `Database` 클래스” 한 개보다 `UserRepository`, `OrgRepository`, `ChatLogRepository`처럼 **작은 단위** |
| **D** 의존성 역전 | UI·도메인은 구체 구현(Firebase SDK 직접)이 아니라 **추상(Protocol)** 에 의존 | 페이지 상단에서 `get_user_repo()`가 `Protocol`을 반환 → 테스트 시 **가짜 저장소** 주입 가능 |

### 10.2 응집도를 높이는 쪽(같은 이유로 바뀌는 코드를 모은다)

- **역할별 페이지** 한 파일 안: 위젯 배치 + `session_state` 읽기/쓰기 + “무엇을 호출할지”만.  
- **`services/rag_pipeline.py`**: 청킹·임베딩·Chroma 키 규칙을 **한곳**에서만 정의.  
- **`services/repositories/`**: Firestore 필드명·컬렉션 경로는 **Repository 파일들**에만 모아 두고, 페이지에는 문자열 리터럴을 흩뿌리지 않기.

### 10.3 결합도를 낮추는 쪽(서로 몰라도 되게)

- **페이지 → 서비스:** `import`는 **함수·클래스의 공개 API**만. SDK 세부 타입은 서비스 내부에 가둠.  
- **인증 vs RAG vs 과금:** 학생 채팅 페이지는 “질문 → 답변 텍스트”만 알면 되고, **슬롯 검증**은 `BillingService` 또는 `OrgService`에만 두기.  
- **Gemini / Chroma:** `gemini_client.py`, `vector_store.py`(또는 `rag_pipeline` 내부)로 분리해, UI는 `answer_question(...)` 한 줄에 가깝게.

### 10.4 Streamlit에 맞는 “의존성 주입” 패턴

전통적인 DI 컨테이너가 없어도 됩니다.

- **`@st.cache_resource`** 로 무거운 클라이언트(Firebase 앱, Chroma 컬렉션 핸들)를 **프로세스당 한 번** 생성.  
- 팩토리 함수 예: `def get_chat_service() -> ChatService:` 내부에서 캐시된 repo를 조립.  
- **테스트:** Streamlit 없이 `services/`의 순수 함수·클래스만 `pytest`로 검증.

### 10.5 폴더에 대한 짧은 매핑

```
pages/          → SRP: 화면·흐름 (얇게)
services/       → 응집: 도메인·외부 연동
services/ports.py   → Protocol 정의 (DIP, ISP)
services/adapters/  → Firebase·Gemini 구체 구현 (필요 시 분리)
```

이렇게 두면 **UI 세팅(섹션 9)** 은 Streamlit 설정·레이아웃에 집중하고, **비즈니스 규칙**은 SOLID에 맞게 `services`에 남겨 **응집도는 높이고 결합도는 낮춘** 구조로 가져갈 수 있습니다.

---

## 11. 발표·제안용 차별화 포인트(원문 요약)

1. **데이터 격리** — Firebase UID·`org_id` 기준으로 기업 간 데이터가 섞이지 않게 설계  
2. **비용 예측** — 학생 수 기반 슬롯으로 AI 비용·규모 통제 논리  
3. **확장성** — Gemini 긴 문맥 + Firebase 실시간 동기화로 대량 교안 대응 메시지  

---

## 12. 구현 스냅샷 (2026-04, 코드 기준)

아래는 **기획 대비 실제 구현된 범위**를 한 번에 보기 위한 요약입니다. 세부 진행·미완은 `1.기획/진행중상황.md`를 본다.

| 영역 | 구현 내용 |
|------|-----------|
| 인증·가입 | **회원가입 시 운영자/유저 선택**, 유저는 학원명 없이 가입 후 **Home에서 초대 코드 소속 신청**. **초대 가입·Home 신청**은 즉시 소속이 아니라 **`JoinRequests` + 운영자 승인** 후 `Teacher`/`Student` 반영. **비밀번호 확인** 필드. `User`·승인 후 역할은 **`refresh_session_from_firestore`** 등으로 세션 동기화 |
| 인증·운영자 | Firebase Auth, `Users`/`Organizations`, 관리 화면(플랜·슬롯·초대·콘텐츠 카테고리·교사 배치). 기업 상세 **AI 토큰 활용량** 탭. **교사·학생 탭**: **가입 승인 대기**, **소속 사용자 목록**(검색·정렬·스크롤 표·행 선택→상세 연동)·상세에서 **정보 변경·삭제**(기본 정보 탭과 유사). **콘텐츠 탭**에서 과목별 **수업 통계**(운영자 모드 시 상단 **AI 토큰 요약**)·**운영자 피드백**·**AI 교사 피드백 초안** |
| 교사 | 수업 선택, **개요**·**학생 관리**·**수업 통계**·**AI 토큰 활용량**·**수업 관리**. 학생 상세에 **통합 퀴즈(연습) 기록**(Firestore 로그). 퀴즈·AI 분석·expander 등; **수업 통계** 탭은 AI 토큰 상세 대신 **AI 토큰 메뉴** 안내 |
| 학생 | 개요, 수업 개요, **주차별 수강** + 퀴즈·진행률 등. **통합 퀴즈** 메뉴: 일괄/무한 연습, **AI 코칭 요약 버튼**, 활동 로그 저장 |
| 데이터·집계 | 상기 + `StudentIntegratedQuizLogs`, `JoinRequests`, 사용자 `membership_pending` 계열. **`aggregate_quiz_stats_for_course`** 등 기존 집계 유지 |
| UX | `session_keys` 상수, 사이드바, 수강 플레이어 `st.fragment`·CSS, AI 본문 expander, 관리 소속 목록 표 상호작용 |
| 과금(현재) | **`max_slots`·`plan`** 중심 — AI 변동비·모델 티어는 **§5.1**에서 확장 검토 중 |
| **AI 사용량(관측)** | **운영·교사 화면**에서 Gemini **입·출력 토큰**·호출 수·세부 기능(`usage_kind`)·**호출자(actor)** 를 집계·검색 가능 — 과금 연동 전 **미터링** 단계 |
| **성능(2026-04)** | Firestore `array_contains`, `st.cache_data`(수업 목록), 사이드바·본문 **중복 조회 제거**, Home `refresh_session` **스로틀**, 미사용 **chromadb** 제거 |
| **UI(배포)** | Matplotlib **번들 나눔고딕 TTF**로 차트 한글 깨짐(□) 방지 |

**아직 기획서 전체와의 갭·보완 포인트**  
- **퀴즈 데이터 일관성**: 구버전 제출만 있고 `quiz_attempt_count` 등이 비어 있으면 UI상 “응시 0회” 등과 불일치할 수 있음 → 재제출 또는 마이그레이션 검토.  
- **오답 지문 표시**: `get_lesson_week`로 읽은 주차에 퀴즈 문항이 없거나 수업 관리와 불일치하면 **지문 미수록** 안내만 표시됨.  
- 운영자 **기업 단위** 대시보드(슬롯 vs 인원 차트 등), **Chroma/RAG**와 수강 AI의 단일 플로우, Streamlit Cloud·**Firestore 보안 규칙** 하드닝 등은 `1.기획/진행중상황.md`의 **보완·다음 단계**를 참고한다.

---

## 13. 공모전 제출 시 기대 평가·유의점 (가설적 정리)

심사 방식·배점이 공개되지 않았으므로 **일반적인 SW·교육 공모전 기준**에서의 추정이다.

| 강점으로 읽힐 수 있는 점 | 설명 |
|--------------------------|------|
| **완성도·범위** | 운영자·교사·학생 **역할 분리**, Firestore **다층 데이터 모델**, 수업·주차·진행률·퀴즈·AI 질문·통합 퀴즈·**토큰 미터링**까지 한 흐름으로 연결된 **교육 SaaS형** 데모 |
| **AI 활용의 실무성** | Gemini를 “보여주기”에 그치지 않고 **호출 단위 추적**(`usage_kind`, actor), **운영·교사** 관점의 **비용·투명성** UI |
| **기획 문서화** | 데이터 모델·역할·로드맵·진행 상황이 문서로 남아 있음 |

| 약점·감점 가능성 | 설명 |
|-------------------|------|
| **기술 스택의 대중성** | Streamlit은 **빠른 검증**에 유리하나, **상용 서비스와 동일한 UX·확장성** 기대를 받으면 “프로토타입”으로 보일 수 있음 |
| **RAG·벡터 검색** | 기획 대비 **Chroma/RAG 본구현**이 스텁에 가깝고, 수강 AI는 **주차 맥락 + Gemini** 중심 → “AI 에이전트·RAG”를 강조하는 심사라면 **설명·로드맵**이 필요 |
| **배포·안정성** | 첫 로딩 지연, Streamlit rerun 특성, **보안 규칙·Secrets** 미비 시 데모 중 오류 가능 |
| **차별성 서술** | 유사한 “학원용 LMS + AI”가 많을 경우 **한 문장 차별점**(예: 토큰 가시화, 승인 워크플로, 통합 퀴즈 로그)을 발표·제출서 **전면**에 둘 것 |

**제출물 관점 제안:** 시연 영상(3~5분)에서 **① 운영자 승인 → 교사 수업 설계 → 학생 수강·질문 → 교사 대시보드** 순서와 **② AI 토큰 화면** 한 컷을 넣으면 스토리가 명확해진다.

---

## 14. AI 활용 추가·보완 아이디어 (우선순위 참고)

기존 기능을 해치지 않는 선에서 **가치 대비 구현량** 순으로 정리했다.

| 우선순위 | 아이디어 | 기대 효과 |
|----------|----------|-----------|
| 높음 | **RAG 본구현** 또는 “주차별 첨부 자료 → 임베딩 → 학생 질문 시 인용” 최소 루프 | 기획서·발표의 “교안 기반 답변”과 일치, 심사 설득력 |
| 높음 | **프롬프트·응답 품질**: 역할별 시스템 프롬프트 정리, 금지어·개인정보 마스킹, 응답 길이·톤 옵션 | AI 응답 일관성·안전성 |
| 중간 | **학습 코치 요약**: 주차·수업 단위로 “이번 주 핵심 3줄·다음 액션” 자동 생성(기존 Gemini 파이프라인 활용) | 학생·교사 모두에게 가시적 가치 |
| 중간 | **이상 징후 알림(교사/운영)**: 질문 0건·진행률 정체·퀴즈 연속 오답 등 **휴리스틱 + LLM 요약 한 줄** | “개인화 생태계” 스토리 보강 |
| 중간 | **토큰 예산·알림**: 플랜별 월 목표 대비 **80%/100%** 배너(이미 집계 인프라 있음) | §5.1 비즈니스와 연결 |
| 낮음·선택 | **음성 입력/요약**, **다국어 UI** | 데모 임팩트; 범위·비용 주의 |
| 공통 | **평가·로그**: 소규모 사용자 테스트 시 질문·오류 로그 수집 → 프롬프트 A/B | 실제 개선에 유리 |

`1.기획/진행중상황.md` §4 **미착수·우선 보완**과 겹치는 항목은 동일 우선순위로 맞추면 된다.

---

**문서 범위:** 원문 `정리폴더/기본정리.md`와 맞추되, **실행 순서·시스템 경계·폴더 역할**(§6~8), Streamlit UI·**SOLID**(§9~10), **구현 스냅샷**(§12), **성능·차트**(§5.2~5.3), **공모전·AI 보완**(§13~14)을 보강해 두었다.
