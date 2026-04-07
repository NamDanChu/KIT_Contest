"""교안 업로드 파일에서 텍스트 추출 (PDF·txt). 영상은 메타만."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from pypdf import PdfReader


def extract_text_from_pdf_bytes(data: bytes) -> str:
    if not data:
        return ""
    try:
        reader = PdfReader(BytesIO(data))
        parts: list[str] = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n".join(parts).strip()
    except Exception:
        return ""


def extract_text_from_txt_bytes(data: bytes) -> str:
    if not data:
        return ""
    for enc in ("utf-8", "utf-8-sig", "cp949"):
        try:
            return data.decode(enc).strip()
        except Exception:
            continue
    return data.decode("utf-8", errors="replace").strip()


def build_combined_source_for_gemini(
    *,
    learning_goals: str,
    pdf_parts: list[tuple[str, bytes]],
    txt_parts: list[tuple[str, bytes]],
    video_names: list[str],
    max_chars: int = 28000,
) -> tuple[str, list[dict[str, Any]]]:
    """Gemini에 넣을 본문 + 업로드 메타(저장용).

    영상은 텍스트 추출 없이 파일명만 본문에 안내 문구로 포함.
    """
    chunks: list[str] = []
    meta: list[dict[str, Any]] = []

    g = (learning_goals or "").strip()
    if g:
        chunks.append(f"[학습 목표·키워드]\n{g}")

    for name, b in pdf_parts:
        t = extract_text_from_pdf_bytes(b)
        if t:
            chunks.append(f"[PDF: {name}]\n{t}")
        meta.append({"filename": name, "kind": "pdf", "extracted_chars": len(t)})

    for name, b in txt_parts:
        t = extract_text_from_txt_bytes(b)
        if t:
            chunks.append(f"[자막·대본: {name}]\n{t}")
        meta.append({"filename": name, "kind": "text", "extracted_chars": len(t)})

    for name in video_names:
        chunks.append(
            f"[영상: {name}]\n(영상 본문은 자동 추출하지 않습니다. 자막·대본 파일을 함께 올리면 AI 학습에 반영됩니다.)"
        )
        meta.append({"filename": name, "kind": "video", "extracted_chars": 0})

    combined = "\n\n---\n\n".join(chunks).strip()
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n\n…(길이 제한으로 이후 생략)"
    return combined, meta
