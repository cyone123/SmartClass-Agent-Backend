---
name: pdf
description: Extract and analyze text and data from PDF. Use when the task involves pdf files.
---

# Analyzing Attachments

Load this skill when the user asks about uploaded pdf.

## Workflow

1. Run `scripts/extract_pdf_text.py` with the pdf file paths.
2. Review the extracted output. If needed, read supporting notes from `references/pdf-workflow.md`.
3. Return a concise summary in plain language, focusing on teaching-relevant content, structure, and any missing context.

## Output guidance

- Mention the likely topic, structure, and important facts found in the files.
- Say clearly when a file could not be read or only partial text was extracted.
- Do not invent content that was not present in the extracted output.
