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
- `pages/` — 역할별 화면 (얇게 유지)
- `services/` — Firebase, Firestore, Gemini, RAG (응집)
- `chroma_data/` — 로컬 Chroma 저장 (git 제외, `.gitkeep`만 추적)
