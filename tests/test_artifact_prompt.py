from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.core.agent import ARTIFACT_EXECUTION_CONTRACT, AgentRuntime


def _prompt(artifact_type: str) -> str:
    runtime = AgentRuntime.__new__(AgentRuntime)
    return runtime._build_artifact_prompt(
        {
            "messages": [HumanMessage(content="请同时生成 PPTX、DOCX 和 HTML")],
            "teaching_design_plan": "固定教学方案",
        },
        artifact_type,
    )


def test_artifact_prompt_isolates_each_branch_and_requires_execution() -> None:
    ppt_prompt = _prompt("ppt")
    docx_prompt = _prompt("docx")
    html_prompt = _prompt("html-game")

    assert "responsible only for the PPTX artifact" in ppt_prompt
    assert "responsible only for the DOCX artifact" in docx_prompt
    assert "responsible only for the HTML artifact" in html_prompt
    assert ARTIFACT_EXECUTION_CONTRACT in ppt_prompt
    assert ARTIFACT_EXECUTION_CONTRACT in docx_prompt
    assert ARTIFACT_EXECUTION_CONTRACT in html_prompt
    assert "AGENT_OUTPUT_DIR" in html_prompt
