# EduChain AI

**AI 에이전트와 클라우드가 맞물린 초개인화 학습**을 목표로 한 교육 SaaS형 데모입니다.  
Firebase로 인증·데이터를 두고, Google **Gemini**로 수업 도구·학습 코칭·통계 분석을 제공하며, **호출 단위 토큰 미터링**으로 AI 사용량을 가시화합니다.

---

## 목차

1. [기술 스택](#기술-스택)  
2. [저장소 구조](#저장소-구조)  
3. [역할별 기능](#역할별-기능)  
4. [구현 방식 요약](#구현-방식-요약)  
5. [빠른 시작](#빠른-시작)  
6. [문서 · AI 협업 프로세스](#문서--ai-협업-프로세스)  
7. [공모전 제출 서류](#공모전-제출-서류)  
8. [라이선스·주의](#라이선스주의)

---

## 기술 스택

| 구분 | 사용 |
|------|------|
| UI | [Streamlit](https://streamlit.io/) (멀티페이지 `pages/`) |
| 인증·DB | Firebase **Authentication** + **Cloud Firestore** (`firebase-admin`) |
| AI | Google **Gemini** (호출마다 `usage_metadata` 기반 토큰 누적) |
| 배포 | Streamlit Cloud 등 (Secrets에 API·서비스 계정 JSON 문자열) |
| 차트 | matplotlib + **번들 나눔고딕** (`EduChain_AI/assets/fonts/`) — Linux 배포 시 한글 깨짐 방지 |

---

## 저장소 구조

```
KIT_Contest/
├── EduChain_AI/           # Streamlit 앱 (실행 루트)
│   ├── Home.py
│   ├── pages/             # 1_Login, 2_관리, 3_Teacher, 4_학생관리, 5_Student
│   ├── services/          # Firestore, Gemini, UI 모듈
│   ├── firebase/
│   └── assets/fonts/      # 차트용 한글 폰트 (OFL)
├── 1.기획/                # 기획·진행·연동 문서 (상세 스펙)
├── 제출서류/              # K.I.T. 바이브코딩 공모전 양식 대응 초안 (기획·AI 활용 전략)
└── 0.AI_협업_자료/        # AI 협업 방식·문서 색인·지침 (공모전 제출용)
```

> 동일 성격의 `AI_협업_자료/` 폴더가 있을 수 있습니다. **권장 읽기 순서**는 `0.AI_협업_자료/README.md`를 기준으로 하면 됩니다.

---

## 역할별 기능

| 역할 | 주요 기능 |
|------|-----------|
| **운영자 (Operator)** | 기업(학원) 등록·플랜·슬롯, 교사·학생 초대·**가입 승인**, 콘텐츠 카테고리·교사 배정, 과목별 **수업 통계**, **AI 토큰 활용량**(기업·수업·사용자·최근 호출), 운영자→교사/학생 피드백 |
| **교사 (Teacher)** | 배정된 수업 선택, **개요**·**학생 관리**·**수업 통계**·**AI 토큰 활용량**·**수업 관리**(주차·영상·퀴즈·AI 생성물), 학생별 AI 학습 분석, 통합 퀴즈(연습) 로그 조회 |
| **학생 (Student)** | **개요**, **수업 개요**·**수업 수강**(주차·영상·진행률), 주차 **AI 질문**(영상 위치 로그), **통합 퀴즈**(일괄/무한·AI 코칭) |
| **유저 (User)** | 소속 전 **초대 코드**로 신청 → 운영자 승인 후 Teacher/Student 전환 |
| **공통** | 이메일·Google 로그인, 역할·기업별 Firestore 격리, 세션 동기화 |

---

## 구현 방식 요약

| 영역 | 방식 |
|------|------|
| **앱 셸** | Streamlit **멀티페이지** + `st.session_state`에 `AUTH_*`·역할·기업 ID 유지 |
| **백엔드 접근** | 서버에서만 `firebase-admin`으로 Firestore 접근(규칙은 클라이언트 직접 접근 시 별도 강화) |
| **Gemini** | `services/gemini_client.py`에서 통합 호출, 성공 시 **입·출력 토큰**을 `Organizations/.../AiTokenRollup`·`AiTokenEvents`에 기록 (`usage_kind`, `bucket`, actor) |
| **수업 AI** | 주차·수업 메타 + Gemini (전역 **RAG/Chroma**는 `rag_pipeline.py` 스텁 — 향후 확장 여지) |
| **성능 (최근)** | 수업 목록 Firestore **`array_contains`**, `st.cache_data`, 사이드바·본문 **중복 조회 제거**, Home 프로필 **`refresh_session` 스로틀** |

자세한 데이터 모델·화면 매핑은 **[`1.기획/EduChain_AI_전체정리.md`](1.기획/EduChain_AI_전체정리.md)** 를 본다.

---

## 빠른 시작

1. **저장소 클론** 후 앱 디렉터리로 이동합니다.

```bash
cd EduChain_AI
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
```

2. **`secrets.toml`** 에 `GEMINI_API_KEY`, Firebase 관련 키를 채웁니다.  
   - 배포 시에는 `FIREBASE_SERVICE_ACCOUNT_JSON` 등 **문자열** 방식이 일반적입니다.  
   - 상세: **[`1.기획/연동필요.md`](1.기획/연동필요.md)**

3. **실행**

```bash
streamlit run Home.py
```

한 줄 요약·PowerShell 예시는 **[`1.기획/개발자_실행.md`](1.기획/개발자_실행.md)** 에도 정리되어 있습니다.

---

## 문서 · AI 협업 프로세스

공모전·제출 시 **기획 문서와 AI 협업 과정**을 함께 보여 주기 위해 폴더를 나누어 두었습니다.

| 위치 | 내용 |
|------|------|
| **[`0.AI_협업_자료/README.md`](0.AI_협업_자료/README.md)** | **권장 읽기 순서** — 협업 프로세스 → 기획 문서 색인 → 코딩 지침 → 구현 이력 |
| **[`1.기획/진행중상황.md`](1.기획/진행중상황.md)** | 완료·미완·다음 작업·기술 부채 |
| **[`1.기획/개발순서.md`](1.기획/개발순서.md)** | 개발 단계·현재 구현 스냅샷 |
| **[`1.기획/심사자용_접속_순서_AI강조.md`](1.기획/심사자용_접속_순서_AI강조.md)** | 심사자용 동선 가이드 (**AI 시나리오 중심**) |
| **[`EduChain_AI/README.md`](EduChain_AI/README.md)** | 앱 전용 실행·Firebase 요약 |

**협업 흐름(요약):** 기획을 `1.기획/`에 정리 → 코드 반영 → 기능 추가 시 동일 폴더·`0.AI_협업_자료` 이력 갱신.

---

## 공모전 제출 서류

**K.I.T. 바이브코딩 공모전** 등 제출용으로, 양식 **「AI 빌딩 리포트」·「AI 활용 전략」** 에 맞춘 초안을 모아 두었습니다.

| 문서 | 설명 |
|------|------|
| [`제출서류/README.md`](제출서류/README.md) | 제출 폴더 안내 |
| [`제출서류/00_표지_메타정보.md`](제출서류/00_표지_메타정보.md) | 팀명·연락처·프로젝트명 플레이스홀더 |
| [`제출서류/01_AI_빌딩_리포트_기획.md`](제출서류/01_AI_빌딩_리포트_기획.md) | **1. 기획** (사용자·문제, 핵심 기능, 기대 효과) |
| [`제출서류/02_AI_활용_전략.md`](제출서류/02_AI_활용_전략.md) | **2. AI 활용 전략** (도구·모델, 도구별 전략, 토큰·유지보수) |
| [`제출서류/03_심사자용_접속_순서.md`](제출서류/03_심사자용_접속_순서.md) | **심사자용** 라이브 확인 순서 (역할별 할 일) |

공식 PDF/한글 양식에 **복사 후** 팀 정보·문구만 조정하면 됩니다.

---

## 라이선스·주의

- 저장소에 포함된 **나눔고딕** 폰트는 `EduChain_AI/assets/fonts/OFL-NanumGothic.txt` 기준 **SIL Open Font License**를 따릅니다.
- API 키·서비스 계정 JSON은 **Git에 커밋하지 마세요.** `.gitignore`와 Streamlit Secrets를 활용합니다.

---

*EduChain AI — KIT Contest 프로젝트 (2026)*
