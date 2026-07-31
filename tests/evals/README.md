# SmartClass 评估系统

该目录提供 Agent 行为评估、严格用例校验、回归门禁和可提交 benchmark 证据。当前数据集共 24 个 YAML 用例；目录名只负责组织文件，分类语义以 YAML 的 `category` 字段为准。

## 当前用例

| Category | 用例数 | 默认运行模式 |
| --- | ---: | --- |
| `intent_recognition` | 5 | `model-eval` |
| `memory_retrieval` | 3 | `model-eval` |
| `memory_write` | 4 | `model-eval` |
| `memory_update` | 1 | `model-eval` |
| `extraction_quality` | 7 | `model-eval` |
| `context_compression` | 4 | `deterministic` |
| **合计** | **24** | |

## 安装与离线门禁

从 `backend` 目录执行：

```bash
python -m pip install -r requirements-dev.txt
python -m tests.evals.cli validate-suite --expected-count 24
python -m pytest tests/evals -q
```

`validate-suite` 不加载模型，也不访问数据库。它会递归发现全部 YAML，并严格检查：

- YAML/Pydantic Schema；
- `case_id` 唯一性；
- category 是否受支持；
- 每个断言是否有注册处理器；
- 断言引用字段是否属于对应 evaluator 的稳定输出契约。

任何解析失败、未知断言、非法字段或期望数量不符都会返回非零退出码，不允许静默跳过。

## 运行真实评估

真实评估需要数据库、模型服务和相应环境变量，不属于普通 push 的强制门禁：

```bash
python -m tests.evals.cli list-categories
python -m tests.evals.cli run --category intent_recognition --local-docker-db
python -m tests.evals.cli run --case-id intent_basic_chat_001 --local-docker-db --verbose
python -m tests.evals.cli run --local-docker-db
```

`--local-docker-db` 用于“Python 在宿主机、PostgreSQL 在本仓库 Compose 中”的运行方式。它从根目录 `.env.docker` 加载数据库账号，并强制通过 `127.0.0.1` 连接，不会输出密码。容器内运行时不要使用该参数。

原始报告写入 `tests/evals/results/`，该目录中的运行结果默认被 Git 忽略。

## 报告契约

当前报告 `schema_version` 为 `2.0`，核心字段包括：

- `run_mode`：`deterministic`、`smoke`、`model-eval` 或 `mixed`；
- `total_cases`、`passed`、`failed`、`error`；
- `pass_rate` 与 `error_rate`；
- `avg_score`，与通过率分开统计；
- `category_metrics`，保存每个 category 的样本量、通过率、错误率和平均分；
- `dataset_fingerprint`、`git_commit`、`repository_dirty`、`source_fingerprint`、非敏感模型角色摘要和运行环境 manifest。未提交改动也会进入源码 SHA-256 指纹，避免仅凭 HEAD 错认实验版本。

完整 suite 同时包含 20 个模型用例和 4 个确定性上下文压缩用例，因此报告必须标记为 `mixed`，并在每个 `category_metrics.*.run_mode` 中保留真实运行模式，不能把确定性结果包装成模型效果。

如果任一 case 发生运行时 `ERROR`，CLI 会在保存原始报告后返回非零退出码。

旧版 JSON 可被读取用于排查，但不能通过回归门禁，也不能直接晋升为新基线。

## 回归门禁

阈值定义在 `regression_thresholds.yaml`。以下条件均采用 fail-closed：

- 缺少任一必需 category；
- 总体或分类存在 `ERROR`；
- 任一分类通过率低于阈值；
- 报告不是 Schema 2.0。

```bash
python -m tests.evals.check_regression \
  --report tests/evals/fixtures/reports/passing.json
```

`fixtures/reports/` 同时包含阈值下降、缺失类别、运行错误和 legacy 失败样例。

## 晋升 benchmark

只有通过回归门禁的新报告才能晋升：

```bash
python -m tests.evals.cli promote-baseline \
  --report tests/evals/fixtures/reports/passing.json \
  --baseline-id my-baseline
```

输出位于根仓库 `docs/benchmarks/baselines/<baseline-id>/`：

- `manifest.yaml`
- `summary.json`
- `report.md`

证据文件只允许聚合指标和非敏感运行元数据，不写入 prompt、completion、记忆正文、附件正文、JWT、签名 URL、对象 key、宿主机路径或完整异常正文。相同 baseline ID 默认不可覆盖；必须显式传入 `--replace`。

## CI

现有 `.github/workflows/integration.yml` 已扩展为：

- `backend-unit`：Ruff + 默认 pytest；
- `eval-harness`：24/24 严格校验 + 评估基础设施测试；
- `eval-regression-smoke`：验证成功与 fail-closed fixtures，并上传脱敏 smoke 证据；
- `frontend-build`：前端依赖安装与构建；
- `compose-smoke`：Compose 配置及后端镜像构建。

普通 push 不读取真实模型 API Key；真实模型评估应使用独立、人工触发的工作流。
