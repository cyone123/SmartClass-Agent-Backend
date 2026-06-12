# 评估系统快速参考卡

## 🚀 一键运行

```bash
cd backend

# 运行所有意图识别评估
python -m tests.evals.cli run --category intent

# 运行单个用例
python -m tests.evals.cli run --case-id intent_basic_chat_001

# 验证用例格式
python -m tests.evals.cli validate tests/evals/cases/intent/basic_chat.yaml
```

## 📊 评估用例列表

| ID | 描述 | 断言数 | 状态 |
|----|------|--------|------|
| `intent_basic_chat_001` | 闲聊意图识别 | 2 | ✅ |
| `intent_teaching_plan_001` | 教学规划意图 | 4 | ⏳ |
| `intent_artifact_revision_001` | 产物修改意图 | 1 | ⏳ |
| `intent_ambiguous_001` | 模糊请求处理 | 1 | ⏳ |
| `intent_mixed_001` | 混合意图识别 | 4 | ⏳ |

## 🔧 断言类型

```yaml
# 路由匹配
- type: "route_match"
  field: "intent"
  expected: "teaching_plan"
  weight: 1.0

# 包含检查
- type: "contains"
  field: "response"
  expected: ["数学", "教学"]
  weight: 0.7

# 不包含检查
- type: "not_contains"
  field: "extracted_elements"
  expected: "subject"
  weight: 0.5

# LLM 评判
- type: "response_quality"
  field: "response"
  rubric: "chat_response"
  min_score: 0.7
  weight: 0.3
```

## 📝 添加新用例

1. 创建 YAML 文件：`tests/evals/cases/<category>/<name>.yaml`
2. 定义用例结构：
```yaml
case_id: intent_new_001
category: intent_recognition
description: "描述"
version: "1.0"

input:
  user_id: "test_user"
  message: "测试消息"

expectations:
  intent: "normal_chat"

assertions:
  - type: "route_match"
    field: "intent"
    expected: "normal_chat"
    weight: 1.0

metadata:
  author: "your_name"
  created_at: "2026-06-11"
  tags: ["intent"]
```
3. 验证：`python -m tests.evals.cli validate <file.yaml>`
4. 运行：`python -m tests.evals.cli run --case-id <case_id>`

## 📁 关键文件

| 文件 | 用途 |
|------|------|
| `app/core/evaluation.py` | 数据模型 |
| `evaluators/base.py` | 评估器基类 |
| `evaluators/intent_evaluator.py` | 意图评估器 |
| `runners/eval_runner.py` | 运行器 |
| `cli.py` | CLI 工具 |
| `cases/intent/*.yaml` | 用例定义 |
| `results/*.json` | 评估结果 |

## ⚙️ 环境要求

- PostgreSQL 数据库运行中
- 配置模型 API（MODEL, API_KEY, BASE_URL）
- Python 3.11+
- 依赖已安装

## 🐛 常见问题

### Windows asyncio 错误
已在 `cli.py` 中修复，使用 `WindowsSelectorEventLoopPolicy`

### Prometheus 依赖缺失
已在 `cli.py` 中禁用，设置 `PROMETHEUS_ENABLED=false`

### 控制台编码错误
已在 `cli.py` 中修复，使用 UTF-8 编码

## 📈 评分规则

- 加权总分 = Σ(断言分数 × 权重) / Σ(权重)
- 权重 ≥ 0.5 的断言必须全部通过才算 PASSED
- 分数范围：0.0 - 1.0

## 📊 报告格式

```json
{
  "suite_id": "eval_1234567890",
  "total_cases": 5,
  "passed": 4,
  "failed": 1,
  "error": 0,
  "avg_score": 0.85,
  "category_scores": {
    "intent_recognition": 0.85
  },
  "execution_time": 120.5,
  "results": [...]
}
```

## 🎯 Phase 1 完成

- ✅ 评估框架
- ✅ 意图识别评估器
- ✅ 5 个基准用例
- ✅ CLI 工具
- ✅ Windows 兼容
- ✅ 首个测试通过

## 📚 文档

- [README.md](./README.md) - 系统概述
- [QUICKSTART.md](./QUICKSTART.md) - 快速开始
- [IMPLEMENTATION_NOTES.md](./IMPLEMENTATION_NOTES.md) - 实现细节
- [FINAL_SUMMARY.md](./FINAL_SUMMARY.md) - 完整总结
