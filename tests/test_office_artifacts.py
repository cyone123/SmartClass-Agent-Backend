from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from app.core.office_artifacts import (
    PRESENTATION_ENTRY,
    PRESENTATIONML_NAMESPACE,
    normalize_pptx_presentation_order,
)


def _child_names(xml: bytes) -> list[str]:
    root = etree.fromstring(xml)
    return [etree.QName(child).localname for child in root]


def test_normalize_pptx_moves_notes_master_before_slide_list(tmp_path: Path) -> None:
    artifact = tmp_path / "slides.pptx"
    presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
    <p:presentation xmlns:p="{PRESENTATIONML_NAMESPACE}">
      <p:sldMasterIdLst/><p:sldIdLst/><p:notesMasterIdLst/><p:sldSz/><p:notesSz/>
    </p:presentation>""".encode()
    with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(PRESENTATION_ENTRY, presentation)
        archive.writestr("sentinel.txt", b"unchanged")

    assert normalize_pptx_presentation_order(artifact) is True

    with zipfile.ZipFile(artifact) as archive:
        names = _child_names(archive.read(PRESENTATION_ENTRY))
        assert names.index("notesMasterIdLst") < names.index("sldIdLst")
        assert archive.read("sentinel.txt") == b"unchanged"

    assert normalize_pptx_presentation_order(artifact) is False
