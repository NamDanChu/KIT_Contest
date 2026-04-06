"""PDF → 청킹 → ChromaDB → 검색 (RAG) 스텁."""

from pathlib import Path

# 로컬 기본 경로 (배포 시 비영속일 수 있음 — 기획 문서 참고)
CHROMA_PERSIST_DIR = Path(__file__).resolve().parent.parent / "chroma_data"


def ingest_pdf(_file_bytes: bytes, _org_id: str) -> None:
    raise NotImplementedError("PDF 파싱·임베딩·Chroma upsert 구현")


def query_similar(_question: str, _org_id: str, _top_k: int = 5) -> list[str]:
    raise NotImplementedError("Chroma 검색 구현")
