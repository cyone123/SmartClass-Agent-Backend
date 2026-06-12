# 评估系统快速参考卡

## 🚀 一键运行

```bash
cd backend

# 运行所有评估
python -m tests.evals.cli run

# 运行特定类别
python -m tests.evals.cli run --category intent       # 意图识别（5个）
python -m tests.evals.cli run --category memory      # 记忆管理（8个）
python -m tests.evals.cli run --category extraction  # 要素抽取（7个）

# 运行单个用例
python -m tests.evals.cli run --case-id memory_complete_001
python -m tests.evals.cli run --case-id extraction_hallucination_001

# 验证用例格式
python -m tests.evals.cli validate tests/evals/cases/memory/load_profile.yaml

# 详细输出
python -m tests.evals.cli run --verbose

# 演示脚本（含样例输出）
python -m tests.evals.demo
```

## 📊 评估用例列表（25个）

### 意图识别（5 个）✅
| ID | 描述 | 断言数 | 状态 |
|----|------|--------|------|
| `intent_basic_chat_001` | 闲聊意图识别 | 2 | ✅ |
| `intent_teaching_plan_001` | 教学规划意图 | 4 | ✅ |
| `intent_artifact_revision_001` | 产物修改意图 | 1 | ✅ |
| `intent_ambiguous_001` | 模糊请求处理 | 1 | ✅ |
| `intent_mixed_001` | 混合意图识别 | 4 | ✅ |

### 记忆检索（4 个）✅
| ID | 描述 | 断言数 | 状态 |
|----|------|--------|------|
| `memory_load_profile_001` | 加载用户画像 | 3 | ✅ |
| `memory_load_experience_001` | 加载教学经验 | 3 | ✅ |
| `memory_no_irrelevant_001` | 忽略无关记忆 | 2 | ✅ |
| `memory_edge_case_001` | 边界情况处理 | 2 | ✅ |

### 记忆写入（4 个）✅
| ID | 描述 | 断言数 | 状态 |
|----|------|--------|------|
| `memory_complete_001` | 完整写入 | 3 | ✅ |
| `memory_update_001` | 更新现有 | 3 | ✅ |
| `memory_privacy_001` | 隐私保护 | 3 | ✅ |
| `memory_not_created_001` | 不应创建 | 2 | ✅ |

### 要素抽取（7 个）✅
| ID | 描述 | 断言数 | 状态 |
|----|------|--------|------|
| `extraction_complete_001` | 完整抽取 | 3 | ✅ |
| `extraction_subject_grade_001` | 学科年级 | 2 | ✅ |
| `extraction_topic_001` | 主题提取 | 2 | ✅ |
| `extraction_incomplete_001` | 不完整处理 | 2 | ✅ |
| `extraction_hallucination_001` | 幻觉检测 | 3 | ✅ |
| `extraction_partial_hallucination_001` | 部分幻觉 | 2 | ✅ |
| `extraction_edge_case_001` | 边界情况 | 2 | ✅ |

## 🔧 断言类型（11 种）

### 基础断言（Phase 1）

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

### 记忆断言（Phase 2）

```yaml
# 记忆加载检查
- type: "memory_loaded"
  namespace: ["users", "test_user", "profile"]
  expected: true
  weight: 1.0

# 记忆不应加载（隐私保护）
- type: "memory_not_loaded"
  namespace: ["users", "other_user", "profile"]
  expected: true
  weight: 0.8

# 记忆内容校验
- type: "memory_content_check"
  namespace: ["users", "test_user", "profile"]
  field: "teaching_style"
  expected: ["interactive"]
  weight: 0.7

# 隐私检查（不包含敏感信息）
- type: "privacy_check"
  field: "memory_content"
  should_not_contain: ["student_name", "phone"]
  weight: 1.0
```

### 抽取断言（Phase 2）

```yaml
# 完整性检查
- type: "extraction_completeness"
  required_fields: ["subject", "grade", "topic"]
  tolerance: 0.8  # 允许缺少 20%
  weight: 1.0

# 准确度评估（LLM）
- type: "extraction_accuracy"
  field: "extracted_elements"
  rubric: "extraction_accuracy"
  min_score: 0.8
  weight: 0.8

# 幻觉检测
- type: "no_hallucination"
  field: "extracted_elements"
  should_not_contain: ["fictional_concept"]
  weight: 1.0
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
| `app/core/evaluation.py` | 评估数据模型 |
| `evaluators/base.py` | 评估器基类 |
| `evaluators/intent_evaluator.py` | 意图评估器 |
| `evaluators/memory_evaluator.py` | 记忆评估器（新） |
| `evaluators/extraction_evaluator.py` | 抽取评估器（新） |
| `runners/eval_runner.py` | 评估运行器 |
| `cli.py` | CLI 工具 |
| `cases/intent/*.yaml` | 意图识别用例 |
| `cases/memory/*.yaml` | 记忆管理用例（新） |
| `cases/extraction/*.yaml` | 要素抽取用例（新） |
| `results/*.json` | 评估结果输出 |

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
  "category": "memory",
  "total_cases": 8,
  "passed": 7,
  "failed": 1,
  "error": 0,
  "avg_score": 0.875,
  "category_scores": {
    "memory_retrieval": 0.88,
    "memory_write": 0.87
  },
  "execution_time": 240.5,
  "results": [...]
}
```

## 📈 评估类别总览

| 类别 | 说明 | 用例数 | 断言类型 | 状态 |
|------|------|--------|---------|------|
| `intent_recognition` | 意图分流 | 5 | 4 种 | ✅ Phase 1 |
| `memory_retrieval` | 记忆加载 | 4 | 3 种 | ✅ Phase 2 |
| `memory_write` | 记忆写入 | 4 | 4 种 | ✅ Phase 2 |
| `extraction_quality` | 要素抽取 | 7 | 4 种 | ✅ Phase 2 |

## 🎯 Phase 1 完成 ✅

- ✅ 评估框架
- ✅ 意图识别评估器
- ✅ 5 个基准用例
- ✅ CLI 工具
- ✅ Windows 兼容
- ✅ 首个测试通过

## 🎯 Phase 2 完成 ✅

- ✅ 记忆评估器（加载 & 写入）
- ✅ 抽取评估器
- ✅ 15 个新用例
- ✅ 7 种新断言类型
- ✅ 回归测试体系
- ✅ 完整文档

## 📚 文档

| 文档 | 内容 |
|------|------|
| [README.md](./README.md) | 系统概述 |
| [QUICKSTART.md](./QUICKSTART.md) | 快速开始 |
| [PHASE2_SUMMARY.md](./PHASE2_SUMMARY.md) | Phase 2 总结（新） |
| [IMPLEMENTATION_NOTES.md](./IMPLEMENTATION_NOTES.md) | 实现细节 |
| [FINAL_SUMMARY.md](./FINAL_SUMMARY.md) | 完整总结 |

## 🔗 回归测试基准

**Phase 1 基准**
- 意图识别准确率：≥ 90%
- 链路响应时间：< 5s
- 用例通过率：100%

**Phase 2 基准**
- 记忆加载准确率：≥ 95%
- 记忆隐私保护：100%
- 抽取完整性：≥ 90%
- 幻觉检测率：≥ 95%
- 整体用例通过率：≥ 95%
