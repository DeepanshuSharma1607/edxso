"""
Extracts plain text from uploaded JD / resume files.
Supports: .pdf, .docx, .txt
"""
import io
from fastapi import UploadFile, HTTPException
from pypdf import PdfReader
from docx import Document


async def extract_text_from_upload(file: UploadFile) -> str:
    filename = (file.filename or "").lower()
    raw = await file.read()

    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if filename.endswith(".pdf"):
        return _extract_pdf(raw)
    elif filename.endswith(".docx"):
        return _extract_docx(raw)
    elif filename.endswith(".txt"):
        return raw.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a .pdf, .docx, or .txt file.",
        )


def _extract_pdf(raw: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {e}")

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="No extractable text found in PDF (it may be a scanned image). "
            "Try pasting the text instead.",
        )
    return text


def _extract_docx(raw: bytes) -> str:
    try:
        doc = Document(io.BytesIO(raw))
        text = "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read DOCX: {e}")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text found in DOCX file.")
    return text


def validate_pasted_text(text: str, field_name: str) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) < 30:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} looks too short — paste the full text.",
        )
    return cleaned
