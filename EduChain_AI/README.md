# EduChain AI (기본 뼈대)

기획: 상위 폴더 `기획/EduChain_AI_전체정리.md`

## 실행

```bash
cd EduChain_AI
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
streamlit run Home.py
```

## 구조

- `Home.py` — 진입점, `set_page_config`
- `pages/` — `1_Login`(로그인·회원가입), `2_관리`(운영자·기업 관리). 교사/학생 화면은 추후 관리 안으로 통합 예정(`views/` 스텁)
- `services/` — `firebase_app.py`(Admin 초기화), `firestore_repo.py`(CRUD), `firebase_web_config.py`(웹 SDK와 동일 설정 dict), Gemini, RAG
- `web/firebase-config.example.js` — 나중에 웹/컴포넌트용 JS 템플릿(실제 `firebase-config.js`는 Git 제외)
- `firebase/firestore.rules` — 콘솔에 붙여 넣을 보안 규칙 초안
- `chroma_data/` — 로컬 Chroma 저장 (git 제외, `.gitkeep`만 추적)

## Firebase

- **Admin (Firestore):** 로컬은 서비스 계정 JSON + `FIREBASE_CREDENTIALS_PATH`, 클라우드는 `FIREBASE_SERVICE_ACCOUNT_JSON`  
- **Auth (이메일·Google):** `FIREBASE_WEB_API_KEY`(= JS `apiKey`) — 콘솔 → 프로젝트 설정 → 일반 → **웹 API 키**  
- **웹 앱 전체 설정:** 콘솔에서 `firebaseConfig` 객체를 복사해 `secrets.toml`의 `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, `FIREBASE_STORAGE_BUCKET`, `FIREBASE_MESSAGING_SENDER_ID`, `FIREBASE_APP_ID`, (선택) `FIREBASE_MEASUREMENT_ID` 에 넣음. Python에서는 `from services.firebase_web_config import get_firebase_web_config` 로 dict 사용 가능.  
- **이메일 로그인:** Authentication → Sign-in method → **이메일/비밀번호** 사용  
- **Google 로그인:**  
  - Firebase Authentication → **Google** 사용  
  - [Google Cloud Console](https://console.cloud.google.com/) → API 및 서비스 → 사용자 인증 정보 → **OAuth 2.0 클라이언트 ID(웹)** 생성  
  - **승인된 리디렉션 URI**에 `GOOGLE_OAUTH_REDIRECT_URI`와 **동일한** 주소 등록  
    - 로컬 예: `http://localhost:8501/`  
    - Streamlit Cloud: `https://<앱이름>.streamlit.app/` (끝 슬래시 포함 여부를 secrets와 콘솔에서 일치)  
  - `secrets.toml`에 `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` 입력  
- **Firestore 규칙:** `firebase/firestore.rules` 를 [콘솔](https://console.firebase.google.com/)에 배포  

개발 순서: `기획/개발순서.md`
