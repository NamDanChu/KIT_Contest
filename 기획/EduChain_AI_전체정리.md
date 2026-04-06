# EduChain AI — 전체 기획 정리

원문: `정리폴더/기본정리.md`를 바탕으로 **해야 할 순서**, **단계별로 쌓이는 시스템**, **구축 대상 시스템**, **파일 구조·메커니즘**을 한곳에 모았습니다.

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
| AI | **Gemini 1.5 Flash** | PDF 분석, 퀴즈 생성, RAG 답변 |
| 벡터 검색 | **ChromaDB** | 교안 임베딩·유사도 검색 |
| 배포 | **Streamlit Cloud** | GitHub 연동 라이브 URL |

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

### `Users`

| 필드 | 설명 |
|------|------|
| `uid` | Firebase Auth UID (PK) |
| `email` | 이메일 |
| `role` | `Teacher` / `Student` / `Operator` |
| `org_id` | 소속 조직 (FK) |

### `ChatLogs`

| 필드 | 설명 |
|------|------|
| `log_id` | 기록 ID |
| `uid` | 학생 ID |
| `query` / `answer` | 질문·답변 |
| `timestamp` | 시각 |

**격리 원칙(발표용 포인트)**  
쿼리·보안 규칙에서 **`org_id`(및 필요 시 `uid`)** 기준으로 데이터가 섞이지 않게 설계한다는 메시지와 맞추면 됨.

---

## 4. 역할별 화면·기능

| 역할 | 핵심 기능 | UI 요약 |
|------|-----------|---------|
| **공통** | 이메일/비밀번호 로그인 | 로그인 후 Firestore `role`로 대시보드 이동 |
| **Teacher** | PDF 업로드 → 키워드·객관식 퀴즈 자동 생성 | 업로드 + 퀴즈 미리보기·편집 |
| **Student** | 교안 기반 RAG Q&A (페이지·맥락 인용) | 좌: 자료 / 우: 챗봇 |
| **Operator** | 가입 학생 수 vs `max_slots`, 질문 빈도 등 | 지표 카드 + 그래프, 슬롯 확장 시연 |

---

## 5. 요금제(비즈니스 모델)

| 플랜 | 월 가격 | 학생 슬롯 | 주요 기능 |
|------|---------|-----------|-----------|
| Starter | 무료 체험 | 5명 | 기본 RAG 채팅(텍스트) |
| Pro | ₩190,000 | 50명 | PDF 분석, AI 퀴즈, 질문 통계 |
| Premium | ₩450,000 | 150명 | 영상 자막 분석(확장), 지원, 슬롯 확장 |

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

- [ ] Firestore 컬렉션·필드 생성 및 **보안 규칙**(조직/역할 기준 읽기·쓰기)  
- [ ] 가입 시 `Users` 문서 생성, `org_id`·`role` 연결 로직  
- [ ] Teacher: PDF → 청크 → 임베딩 → ChromaDB, 퀴즈 생성 프롬프트  
- [ ] Student: 질의 → 벡터 검색 → 컨텍스트 + Gemini 답변, `ChatLogs` append  
- [ ] Operator: 집계 쿼리(또는 Cloud Function) + 슬롯 시연(데모면 Firestore 필드 업데이트로도 가능)  
- [ ] 환경 변수: Firebase 키, Gemini API 키, Chroma 저장 경로(클라우드에서는 영속 볼륨 또는 제약 안내)  

---

## 8. 파일 구조·메커니즘(권장안)

원문에 폴더 명세는 없으므로, **Streamlit + Firebase + RAG** 조합에 흔히 쓰는 구조를 제안합니다. 프로젝트 생성 후 실제 파일명은 팀에 맞게 조정하면 됩니다.

```
KIT_Contest/
├── 기획/
│   └── EduChain_AI_전체정리.md    # 본 문서
├── 정리폴더/
│   └── 기본정리.md
├── app/                            # (선택) Streamlit 진입점 분리 시
│   └── main.py                     # st.set_page_config, 라우팅/세션
├── pages/                          # Streamlit 멀티페이지 시
│   ├── 1_로그인.py
│   ├── 2_교사.py
│   ├── 3_학생.py
│   └── 4_운영자.py
├── services/                       # 비즈니스 로직
│   ├── firebase_auth.py            # 로그인·토큰·세션
│   ├── firestore_repo.py           # Organizations / Users / ChatLogs CRUD
│   ├── rag_pipeline.py             # PDF 로드, 청킹, Chroma upsert, query
│   └── gemini_client.py            # 퀴즈·채팅 호출
├── chroma_data/                    # 로컬 Chroma persist (gitignore 권장)
├── .streamlit/
│   └── secrets.toml                # API 키 (로컬만, 저장소에 커밋 금지)
├── requirements.txt
├── firebase-service-account.json   # 서버용 시 (절대 공개 저장소에 올리지 말 것)
└── README.md
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
| 실행 | 저장소 루트에서 `streamlit run Home.py` **또는** `streamlit run app/main.py` 중 하나로 고정 |
| 멀티페이지 | `pages/` 폴더에 `1_로그인.py`, `2_교사.py` … 첫 숫자가 **사이드바 순서** |
| 단일 진입 | `Home.py`(또는 `app/main.py`)에서만 `st.set_page_config`를 호출하고, 나머지 페이지는 **중복 호출하지 않기**(Streamlit 권장 패턴: config는 최상단 한 번) |

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

이 문서는 `정리폴더/기본정리.md`와 동일한 범위를 유지하면서, **실행 순서·시스템 경계·폴더 역할**을 보강했고, **섹션 9·10**에서 Streamlit UI 세팅과 **SOLID·응집/결합** 원칙을 추가했습니다. 세부 파일명은 첫 커밋 시점에 맞춰 `기획` 문서를 한 번 더 고치면 됩니다.
