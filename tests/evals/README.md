# SmartClass 评估系统

## 概述

评估系统用于验证 Agent 行为的正确性、稳定性和安全性。

## 目录结构

```
tests/evals/
├── cases/              # 评估用例
│   └── intent/         # 意图识别用例
├── evaluators/         # 评估器实现
├── runners/            # 评估运行器
├── rubrics/            # 评分标准
├── results/            # 评估结果
└── cli.py              # CLI 工具
```

## 使用方式

### 运行所有评估

```bash
cd backend
python -m tests.evals.cli run
```

### 运行特定类别

```bash
python -m tests.evals.cli run --category intent
```

### 运行特定用例

```bash
python -m tests.evals.cli run --case-id intent_basic_chat_001
```

### 验证用例格式

```bash
python -m tests.evals.cli validate tests/evals/cases/intent/basic_chat.yaml
```

## 评估用例格式

每个用例是一个 YAML 文件，包含：

- **case_id**: 唯一标识符
- **category**: 类别（如 intent_recognition）
- **description**: 描述
- **input**: 测试输入
- **context**: 上下文设置
- **expectations**: 期望结果
- **assertions**: 断言规则
- **metadata**: 元数据

## 断言类型

- `route_match`: 路由匹配
- `contains`: 包含检查
- `not_contains`: 不包含检查
- `response_quality`: 响应质量评估（使用 LLM 评判）

## Phase 1 已实现

- ✅ 评估目录结构
- ✅ 基础评估框架（base evaluator + runner）
- ✅ 5 个意图识别基准用例
- ✅ 意图识别评估器
- ✅ CLI 工具

## 下一步

- Phase 2: 记忆检索与写入评估
- Phase 3: 产物生成与修改评估
