# SmartClass 评估系统

## 概述

评估系统用于验证 Agent 行为的正确性、稳定性和安全性。支持多维度评估，包括意图识别、记忆管理、教学要素抽取等。

**当前进度：Phase 2 ✅ 完成**

## 快速开始

```bash
cd backend

# 运行所有评估
python -m tests.evals.cli run

# 运行特定类别
python -m tests.evals.cli run --category memory
python -m tests.evals.cli run --category extraction

# 运行单个用例
python -m tests.evals.cli run --case-id memory_complete_001

# 查看详细输出
python -m tests.evals.cli run --verbose
```

## 目录结构

```
tests/evals/
├── cases/                          # 评估用例（25 个）
│   ├── intent/                     # 意图识别（5 个）
│   ├── memory/                     # 记忆管理（8 个）
│   └── extraction/                 # 要素抽取（7 个）
├── evaluators/                     # 评估器实现
│   ├── base.py                     # 基类
│   ├── intent_evaluator.py        # 意图评估器
│   ├── memory_evaluator.py        # 记忆评估器 (新)
│   ├── extraction_evaluator.py    # 抽取评估器 (新)
│   └── test_*.py                  # 单元测试
├── runners/                        # 评估运行器
│   └── eval_runner.py
├── rubrics/                        # 评分标准
│   └── *.yaml
├── results/                        # 评估结果
└── cli.py                          # CLI 工具
```

## 评估类别与用例

| 类别 | 描述 | 用例数 | 状态 | 评估维度 |
|------|------|--------|------|---------|
| `intent_recognition` | 意图识别 | 5 | ✅ | 路由分流、响应质量 |
| `memory_retrieval` | 记忆检索 | 4 | ✅ | 加载准确性、隐私保护 |
| `memory_write` | 记忆写入 | 4 | ✅ | 内容完整性、安全性 |
| `extraction_quality` | 要素抽取 | 7 | ✅ | 完整性、准确度、无幻觉 |
| **总计** | | **25** | **✅** | **11 种断言类型** |

## 评估用例详情

### 意图识别（Phase 1 ✅）
- `intent_basic_chat_001` - 基础闲聊
- `intent_teaching_plan_001` - 教学规划
- `intent_artifact_revision_001` - 产物修改
- `intent_ambiguous_001` - 模糊请求
- `intent_mixed_001` - 混合意图

### 记忆检索（Phase 2 ✅）
- `memory_load_profile_001` - 加载用户画像
- `memory_load_experience_001` - 加载教学经验
- `memory_no_irrelevant_001` - 忽略无关记忆
- `memory_edge_case_001` - 边界情况

### 记忆写入（Phase 2 ✅）
- `memory_complete_001` - 完整写入
- `memory_update_001` - 更新现有记忆
- `memory_privacy_001` - 隐私保护检查
- `memory_not_created_001` - 不应创建

### 要素抽取（Phase 2 ✅）
- `extraction_complete_001` - 完整抽取
- `extraction_subject_grade_001` - 学科年级
- `extraction_topic_001` - 主题提取
- `extraction_incomplete_001` - 不完整处理
- `extraction_hallucination_001` - 幻觉检测
- `extraction_partial_hallucination_001` - 部分幻觉
- `extraction_edge_case_001` - 边界情况

## 断言类型

### 基础断言（Phase 1）
- `route_match` - 路由匹配
- `contains` - 包含检查
- `not_contains` - 不包含检查
- `response_quality` - 响应质量（LLM 评判）

### 记忆断言（Phase 2）
- `memory_loaded` - 记忆加载检查
- `memory_not_loaded` - 记忆不应加载
- `memory_content_check` - 记忆内容校验
- `privacy_check` - 隐私检查

### 抽取断言（Phase 2）
- `extraction_completeness` - 完整性检查
- `extraction_accuracy` - 准确度评估
- `no_hallucination` - 幻觉检测

## 使用方式

### 运行评估

```bash
# 所有评估
python -m tests.evals.cli run

# 特定类别
python -m tests.evals.cli run --category memory
python -m tests.evals.cli run --category extraction

# 特定用例
python -m tests.evals.cli run --case-id memory_complete_001

# 详细输出
python -m tests.evals.cli run --verbose
```

### 验证用例

```bash
python -m tests.evals.cli validate tests/evals/cases/memory/load_profile.yaml
```

### 演示脚本

```bash
python -m tests.evals.demo
```

## 评估用例格式

每个用例是一个 YAML 文件，包含：

```yaml
case_id: memory_complete_001
category: memory_write
description: "完整的记忆写入评估"
version: "1.0"

input:
  user_id: "test_user"
  message: "请记住我偏好互动式教学"

context:
  plan_id: "plan_123"
  thread_id: "thread_456"

expectations:
  memory_created: true
  memory_type: "profile"

assertions:
  - type: "memory_loaded"
    namespace: ["users", "test_user", "profile"]
    expected: true
    weight: 1.0

metadata:
  author: "eval_team"
  created_at: "2026-06-12"
  tags: ["memory", "write"]
```

## 项目阶段

### Phase 1 ✅
- 评估框架
- 意图识别评估器
- 5 个基准用例
- CLI 工具
- Windows 兼容

### Phase 2 ✅
- 记忆评估器（加载 & 写入）
- 抽取评估器
- 15 个新用例
- 7 种新断言类型
- 回归测试体系
- 完整文档

### Phase 3 📋
- 产物生成与修改评估
- 安全性与权限评估
- 性能基准测试
- CI/CD 集成

## 文档

| 文档 | 用途 |
|------|------|
| [QUICKSTART.md](./QUICKSTART.md) | 快速开始指南 |
| [CHEATSHEET.md](./CHEATSHEET.md) | 快速参考卡 |
| [PHASE2_SUMMARY.md](./PHASE2_SUMMARY.md) | Phase 2 完成总结 |
| [IMPLEMENTATION_NOTES.md](./IMPLEMENTATION_NOTES.md) | 实现细节 |
| [FINAL_SUMMARY.md](./FINAL_SUMMARY.md) | 完整技术总结 |

## 环境要求

- PostgreSQL 数据库运行中
- 配置模型 API（MODEL, API_KEY, BASE_URL）
- Python 3.11+
- 依赖已安装

## 常见问题

### Windows asyncio 错误
已在 `cli.py` 中修复，使用 `WindowsSelectorEventLoopPolicy`

### Prometheus 依赖缺失
已在 `cli.py` 中禁用，设置 `PROMETHEUS_ENABLED=false`

### 控制台编码错误
已在 `cli.py` 中修复，使用 UTF-8 编码

## 评分规则

- 加权总分 = Σ(断言分数 × 权重) / Σ(权重)
- 权重 ≥ 0.5 的断言必须全部通过才算 PASSED
- 分数范围：0.0 - 1.0

## 下一步

- 集成到 CI/CD 流程
- 构建评估基准数据库
- 实现自动回归检测
- 添加 Phase 3 产物生成评估
