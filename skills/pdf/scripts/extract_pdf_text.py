from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader
from docx import Document

MAX_CHARS_PER_FILE = 4000


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            chunks.append(text.strip())
    combined = "\n\n".join(chunks).strip()
    if len(combined) > MAX_CHARS_PER_FILE:
        combined = combined[:MAX_CHARS_PER_FILE] + "\n...[truncated]"
    return f"pages={len(reader.pages)}\n{combined}" if combined else f"pages={len(reader.pages)}\n<no extractable text>"

# def extract_docx_text(path: Path) -> str:
#     doc = Document(path)
#     text = ""
#     for para in doc.paragraphs:
#         text += para.text + "\n"
#     return text

def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    # if suffix == ".docx":
    #     return extract_docx_text(path)

    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "<binary file: no text preview>"

    if len(raw) > MAX_CHARS_PER_FILE:
        raw = raw[:MAX_CHARS_PER_FILE] + "\n...[truncated]"
    return raw.strip() or "<empty text file>"


def main() -> int:
    file_args = sys.argv[1:]
    if not file_args:
        print("No attachment file paths were provided.", file=sys.stderr)
        return 1

    for raw_path in file_args:
        path = Path(raw_path).expanduser()
        print(f"=== FILE: {path} ===")
        if not path.exists():
            print("<missing file>")
            continue
        if not path.is_file():
            print("<not a file>")
            continue

        try:
            print(extract_text(path))
        except Exception as exc:
            print(f"<failed to extract: {exc}>")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
