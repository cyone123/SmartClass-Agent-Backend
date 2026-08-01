from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

PRESENTATIONML_NAMESPACE = "http://schemas.openxmlformats.org/presentationml/2006/main"
PRESENTATION_ENTRY = "ppt/presentation.xml"


def normalize_pptx_presentation_order(path: Path) -> bool:
    """Repair the known pptxgenjs notes-master ordering issue in place.

    ISO/IEC 29500 requires ``notesMasterIdLst`` to precede ``sldIdLst``.
    Some generated decks put the notes-master list after the slide list, which
    Office applications may tolerate but strict OOXML validation rejects.
    """

    path = Path(path)
    with zipfile.ZipFile(path, "r") as source:
        presentation_xml = source.read(PRESENTATION_ENTRY)

    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(presentation_xml, parser=parser)
    notes_master = root.find(f"{{{PRESENTATIONML_NAMESPACE}}}notesMasterIdLst")
    slide_list = root.find(f"{{{PRESENTATIONML_NAMESPACE}}}sldIdLst")
    if notes_master is None or slide_list is None:
        return False

    children = list(root)
    notes_index = children.index(notes_master)
    slide_index = children.index(slide_list)
    if notes_index < slide_index:
        return False

    root.remove(notes_master)
    root.insert(slide_index, notes_master)
    normalized_xml = etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=False,
    )

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)

        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(temp_path, "w") as target:
            target.comment = source.comment
            for entry in source.infolist():
                payload = normalized_xml if entry.filename == PRESENTATION_ENTRY else source.read(entry.filename)
                target.writestr(entry, payload)

        os.replace(temp_path, path)
        return True
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
