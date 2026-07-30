# SmartClass 评估系统快速开始

以下命令均从 `backend` 目录执行。

## 1. 安装开发依赖

```bash
python -m pip install -r requirements-dev.txt
```

## 2. 先运行阶段 0 离线门禁

```bash
python -m tests.evals.cli validate-suite --expected-count 24
python -m pytest tests/evals -q
```

严格校验应显示 24 个用例：

- `intent_recognition`: 5
- `memory_retrieval`: 3
- `memory_write`: 4
- `memory_update`: 1
- `extraction_quality`: 7
- `context_compression`: 4

这两步不需要真实模型 Key。它们验证用例发现、Schema、断言注册、字段契约、报告统计、回归门禁和证据脱敏。

## 3. 查看或运行评估

```bash
python -m tests.evals.cli list-categories
python -m tests.evals.cli run --category context_compression
python -m tests.evals.cli run --category intent_recognition
python -m tests.evals.cli run --case-id intent_basic_chat_001 --verbose
```

除确定性用例外，`run` 会调用真实 LangGraph/模型链路，并可能需要数据库。请确认环境变量和依赖服务后再运行。

## 4. 检查回归门禁

```bash
python -m tests.evals.check_regression \
  --report tests/evals/fixtures/reports/passing.json
```

门禁依据分类 `pass_rate`，不使用 `avg_score` 代替通过率。缺少分类、存在运行错误、阈值下降或 legacy 报告都应失败。

## 5. 晋升可提交基线

```bash
python -m tests.evals.cli promote-baseline \
  --report tests/evals/fixtures/reports/passing.json \
  --baseline-id stage0-local-check
```

晋升结果只包含聚合数据，输出到 `docs/benchmarks/baselines/stage0-local-check/`。原始运行 JSON 继续留在被 Git 忽略的 `tests/evals/results/`。

## 6. 报告字段

Schema 2.0 报告应至少包含：

```text
schema_version
run_mode
total_cases / passed / failed / error
pass_rate / error_rate / avg_score
category_metrics
dataset_fingerprint
git_commit
model / environment / manifest
```

`deterministic`、`smoke` 与 `model-eval` 不可混写为同一种证据。确定性 smoke 只证明评估系统与门禁可运行，不代表真实模型质量或时延。
