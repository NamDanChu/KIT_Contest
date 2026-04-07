# GitHub 업로드·정리 가이드

이 문서는 **KIT_Contest** 저장소를 GitHub에 올리기 전에 확인할 항목과, 초기 푸시까지의 절차를 정리한 것입니다.  
앱 실행·키 설정의 세부는 `EduChain_AI/README.md`, `기획/연동필요.md`를 참고합니다.

---

## 1. 저장소 구조 (업로드 단위)

| 경로 | 설명 |
|------|------|
| `EduChain_AI/` | Streamlit 앱 본체 (`Home.py`, `pages/`, `services/` 등) |
| `기획/` | 기획·진행 상황·연동 체크리스트 문서 |
| `정리폴더/` | (선택) 참고 자료·예제 — **용량·저작권** 확인 후 커밋 여부 결정 |

**한 저장소에 루트·앱·기획을 함께 두는 경우**가 기본이며, GitHub에는 **비밀 값이 포함된 파일이 없는지**가 가장 중요합니다.

---

## 2. 올리기 전 필수 체크리스트

### 2.1 비밀·로컬 전용 파일 (커밋 금지)

다음이 **추적되지 않거나**, 이미 커밋돼 있다면 `git rm --cached`로 제거 후 키를 **재발급**하세요.

- [ ] `EduChain_AI/.streamlit/secrets.toml`
- [ ] Firebase **서비스 계정 JSON** (`*firebase-adminsdk*.json`, `firebase-service-account.json` 등)
- [ ] `credentials.json`, `client_secret*.json`, `token.json` (OAuth·GCP)
- [ ] `EduChain_AI/web/firebase-config.js` (예시는 `firebase-config.example.js`만 커밋)
- [ ] `.env`, `.env.local`

제외 규칙은 **`EduChain_AI/.gitignore`** 및 저장소 루트 **`KIT_Contest/.gitignore`**에 정의되어 있습니다.

### 2.2 추적 해제 예시 (이미 커밋된 경우)

PowerShell, 저장소 루트(`KIT_Contest`)에서:

```powershell
git rm --cached EduChain_AI/.streamlit/secrets.toml
git rm --cached -- EduChain_AI/*firebase-adminsdk*.json
```

경로는 실제 파일명에 맞게 조정합니다. 이후 `.gitignore`가 해당 파일을 가리키는지 확인하고 커밋합니다.

### 2.3 커밋해도 되는 것

- [ ] `EduChain_AI/.streamlit/secrets.toml.example` (키 없는 템플릿)
- [ ] `EduChain_AI/.streamlit/config.toml` (테마 등 비밀 아님)
- [ ] `EduChain_AI/firebase/firestore.rules` (규칙 초안 — 콘솔에 배포용)
- [ ] `EduChain_AI/firebase.json`, `.firebaserc` (프로젝트 연결 정보 — 민감하면 팀 정책에 따름)

---

## 3. Git 초기화·원격·첫 푸시 (요약)

로컬에 Git이 없다면 저장소 **루트**에서:

```powershell
cd C:\project\KIT_Contest
git init
git add .
git status
```

`git status`에 **secrets·JSON 키**가 보이면 안 됩니다. 보이면 `.gitignore`를 고치거나 `git reset`으로 스테이징을 취소합니다.

```powershell
git commit -m "Initial commit: EduChain AI 및 기획 문서"
git branch -M main
git remote add origin https://github.com/<사용자명>/<저장소명>.git
git push -u origin main
```

GitHub에서 저장소를 **먼저 빈 저장소로 만들고**, 위 `remote`·`push`를 사용합니다. SSH를 쓰는 경우 `git@github.com:...` 형식으로 `remote add` 합니다.

---

## 4. 이후 협업·배포 시 참고

- **Streamlit Cloud**: GitHub 연동 시 Secrets에 `GEMINI_API_KEY`, Firebase 관련 키 등을 등록 — `기획/연동필요.md` §4·§4.1
- **Firestore 규칙**: `firebase/firestore.rules`를 Firebase 콘솔에 **배포**해야 클라이언트 SDK 접근에 반영됩니다.
- **문서 동기화**: 구현이 바뀌면 `기획/진행중상황.md`, 필요 시 `EduChain_AI/README.md`를 함께 갱신하는 것을 권장합니다.

---

## 5. 관련 파일

| 파일 | 용도 |
|------|------|
| `EduChain_AI/.gitignore` | 앱 폴더 기준 제외 목록 |
| `KIT_Contest/.gitignore` (루트) | 전체 저장소 공통 제외 |
| `기획/연동필요.md` | API 키·Firebase·Streamlit Secrets |
| `기획/진행중상황.md` | 기능 진행·다음 작업 |
| `기획/EduChain_AI_전체정리.md` | 프로젝트 개요·데이터 모델 |

---

*마지막으로 `git status`와 GitHub 웹의 **Files changed**에서 한 번 더 비밀 파일이 없는지 확인한 뒤 푸시하세요.*
