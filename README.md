# SmartClass Agent Backend

<div align="center">

**🎓 SmartClass 教学智能体后端**（FastAPI · LangGraph · PGVector · MinIO）

[![CI](https://github.com/cyone123/SmartClass-Agent-Backend/actions/workflows/ci.yml/badge.svg)](https://github.com/cyone123/SmartClass-Agent-Backend/actions/workflows/ci.yml)
[![Agent Evaluation](https://github.com/cyone123/SmartClass-Agent-Backend/actions/workflows/eval.yml/badge.svg)](https://github.com/cyone123/SmartClass-Agent-Backend/actions/workflows/eval.yml)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-purple.svg)](https://github.com/langchain-ai/langgraph)

</div>

---

## 概述

SmartClass Agent 后端，提供对话式教学智能体的核心服务：LangGraph Agent 工作流、RAG 检索、长期记忆、产物生成（PPT / DOCX / HTML 互动）、对象存储抽象与 JWT 认证。详见 super-repo [SmartClass-Agent](https://github.com/cyone123/SmartClass-Agent)。

## CI 门禁

| Workflow | 触发 | 作用 |
| --- | --- | --- |
| [`ci.yml`](.github/workflows/ci.yml) | push / PR | ruff lint + format check、pytest（Ubuntu + Windows 双平台矩阵）、覆盖率 |
| [`eval.yml`](.github/workflows/eval.yml) | PR / 每日定时 / 手动 | pgvector 服务容器 + Agent 评估套件 + `check_regression` 阈值回归门禁 |

L1 确定快速免费（每次提交）；L2 非确定慢花钱（低频 + 定时巡检），用阈值而非快照对抗模型非确定性。

## 本地开发

```bash
pip install -r requirements.txt
python -m ruff check app tests        # lint
python -m ruff format --check app tests  # format check
python -m pytest tests -q             # 单测（默认排除 tests/evals）
python -m tests.evals.cli list-categories  # 评估用例
```
