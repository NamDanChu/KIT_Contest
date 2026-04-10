# EduChain AI (기본 뼈대)

기획 문서: 상위 폴더 **`1.기획/EduChain_AI_전체정리.md`**

## 실행

```bash
cd EduChain_AI
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
streamlit run Home.py
```

로컬 명령만 모은 안내는 **`1.기획/개발자_실행.md`** 참고.

## 구조

- `Home.py` — 진입점, `set_page_config`
- `pages/` — `1_Login`, `2_관리`, `3_Teacher`, `4_학생관리`, `5_Student` — 멀티페이지 내비
- `services/` — `firebase_app.py`(Admin), `firestore_repo.py`, `firebase_web_config.py`, `gemini_client.py`, `student_portal.py`, `ai_usage_ui.py` 등
- `views/` — placeholder·보조
- `assets/fonts/` — Matplotlib 한글 차트용 **NanumGothic-Regular.ttf**(배포 환경 대비)
- `web/firebase-config.example.js` — 웹 SDK 템플릿(실제 `firebase-config.js`는 Git 제외)
- `firebase/firestore.rules` — 콘솔에 배포할 보안 규칙 초안
- `chroma_data/` — 로컬 Chroma 저장(git 제외, `.gitkeep`만 추적). 현재 RAG는 스텁 위주.

## Firebase

- **Admin (Firestore):** 로컬은 서비스 계정 JSON + `FIREBASE_CREDENTIALS_PATH`, 클라우드는 **`FIREBASE_SERVICE_ACCOUNT_JSON`** (JSON 문자열) 권장 — `services/firebase_app.py` 참고  
- **Auth (이메일·Google):** `FIREBASE_WEB_API_KEY`(= JS `apiKey`) — 콘솔 → 프로젝트 설정 → 일반 → **웹 API 키**  
- **웹 앱 전체 설정:** 콘솔에서 `firebaseConfig` 객체를 복사해 `secrets.toml`의 `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, …  
- **이메일 / Google 로그인·OAuth URI** — `1.기획/연동필요.md` §4.1  
- **Firestore 규칙:** `firebase/firestore.rules` 를 [콘솔](https://console.firebase.google.com/)에 배포  

개발 순서·진행 현황: **`1.기획/개발순서.md`**, **`1.기획/진행중상황.md`**
