# SmartClass 评估系统快速开始

## 🚀 快速开始

### 1. 查看演示
```bash
cd backend
python tests/evals/demo.py
```

### 2. 验证用例格式
```bash
python -m tests.evals.cli validate tests/evals/cases/intent/basic_chat.yaml
```

### 3. 运行评估（需要数据库和模型服务）
```bash
# 运行所有意图识别评估
python -m tests.evals.cli run --category intent

# 运行单个用例
python -m tests.evals.cli run --case-id intent_basic_chat_001

# 详细输出
python -m tests.evals.cli run --category intent --verbose
```

## 📋 已实现的用例

### 意图识别评估 (5个)

| 用例ID | 描述 | 断言数 |
|--------|------|--------|
| intent_basic_chat_001 | 基础闲聊意图识别 | 2 |
| intent_teaching_plan_001 | 教学规划意图识别 | 4 |
| intent_artifact_revision_001 | 产物修改意图识别 | 1 |
| intent_ambiguous_001 | 模糊请求处理 | 1 |
| intent_mixed_001 | 混合意图识别 | 4 |

## 🔧 断言类型

- **route_match**: 精确路由匹配（如 intent == "teaching_plan"）
- **contains**: 字段包含检查（如响应包含"数学"）
- **not_contains**: 字段不包含检查（如不应提取教学要素）
- **response_quality**: LLM评判响应质量（使用 rubric）

## 📊 评估报告

运行后会生成 JSON 格式的报告：
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
  "execution_time": 12.5,
  "results": [...]
}
```

## 🎯 评分规则

- 每个断言有权重（weight）
- 计算加权总分：Σ(断言分数 × 权重) / Σ(权重)
- 权重 ≥ 0.5 的断言必须全部通过才算 PASSED

## 📝 添加新用例

1. 在 `tests/evals/cases/<category>/` 创建 YAML 文件
2. 定义 input、context、expectations、assertions
3. 运行验证：`python -m tests.evals.cli validate <file.yaml>`

示例：
```yaml
case_id: intent_new_001
category: intent_recognition
description: "新的意图识别测试"
version: "1.0"

input:
  user_id: "test_user"
  plan_id: null
  thread_id: "test_thread"
  message: "测试消息"
  attachments: []

context:
  user_profile:
    role: "teacher"

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
  tags: ["intent", "test"]
```

## 🔍 调试技巧

### 查看详细断言结果
```bash
python -m tests.evals.cli run --case-id intent_basic_chat_001 --verbose
```

### 检查用例格式
```bash
python -m tests.evals.cli validate tests/evals/cases/intent/*.yaml
```

### 查看评估报告
```bash
# 报告保存在
cat tests/evals/results/eval_*.json | jq .
```

## ⚠️ 注意事项

1. **需要服务运行**: 评估会实际调用 LangGraph，需要：
   - PostgreSQL 数据库
   - 模型 API 配置
   - 相关环境变量

2. **Windows 编码**: 已处理控制台编码问题，使用 UTF-8

3. **异步执行**: 评估器使用 async/await，会实际运行 Agent

4. **结果保存**: 所有结果保存在 `tests/evals/results/`

## 🚀 Phase 2 计划

- [ ] 记忆检索与写入评估
- [ ] 教学要素抽取评估
- [ ] 建立回归测试集
- [ ] 集成到 CI/CD

## 📚 参考文档

- [评估系统架构](./README.md)
- [Phase 1 总结](./PHASE1_SUMMARY.md)
- [CLAUDE.md 评估章节](../../../CLAUDE.md#7-下一阶段开发重点)
