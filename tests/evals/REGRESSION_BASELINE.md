# 回归测试基准文档

## 概述

本文档定义了 SmartClass Agent 的回归测试基准集和检查流程。

**目的**：
- 确保每次代码变更都不会破坏已有能力
- 建立明确的质量门槛，允许合并前进行自动检查
- 为 Phase 2+ 的特性增强提供稳定的基准

**维护者**：Evaluation Team  
**最后更新**：2026-06-12  
**当前版本**：1.0

---

## Phase 1 基准用例（5个）

意图识别是系统的核心路由机制，必须 100% 准确。

| Case ID | 描述 | 类别 | 预期分数 | 优先级 | 状态 |
|---------|------|------|---------|--------|------|
| `intent_basic_chat_001` | 闲聊意图识别 | intent_recognition | 1.0 | **CRITICAL** | ✅ |
| `intent_teaching_plan_001` | 教学规划意图识别 | intent_recognition | 1.0 | **CRITICAL** | ✅ |
| `intent_artifact_revision_001` | 产物修改意图识别 | intent_recognition | 1.0 | **CRITICAL** | ✅ |
| `intent_ambiguous_001` | 模糊请求处理 | intent_recognition | ≥0.7 | HIGH | ✅ |
| `intent_mixed_001` | 混合意图识别 | intent_recognition | ≥0.8 | HIGH | ✅ |

### Phase 1 用例详情

#### intent_basic_chat_001
- **输入**：天气好心情也好
- **期望行为**：路由到 `normal_chat`，不抽取教学要素
- **关键断言**：`route_match(intent=normal_chat)`, `not_contains(extracted_elements.subject)`
- **失败原因示例**：系统误判为教学规划；不必要地抽取科目信息

#### intent_teaching_plan_001
- **输入**：我想为初中学生设计一节关于勾股定理的数学课，课时 1 节
- **期望行为**：路由到 `teaching_plan`，抽取学科/年级/课题
- **关键断言**：`route_match(intent=teaching_plan)`, `contains(subject=数学)`, `contains(grade=初中)`
- **失败原因示例**：系统误判为闲聊；未能识别教学规划意图

#### intent_artifact_revision_001
- **输入**：把课件的第 3 页改成蓝色主题
- **期望行为**：路由到 `artifact_revision`，提示当前无可修改产物
- **关键断言**：`route_match(intent=artifact_revision)`
- **失败原因示例**：系统误判为教学规划；未能正确识别修改意图

#### intent_ambiguous_001
- **输入**：帮我想想怎样才能讲好这个知识点
- **期望行为**：优先判为教学规划（因为指向教学改进），可能需要追问
- **关键断言**：`route_match(intent=teaching_plan)`，允许分数 ≥0.7
- **失败原因示例**：系统误判为闲聊；路由犹豫导致响应模糊

#### intent_mixed_001
- **输入**：初中数学二次函数这节课怎样设计比较好，我想要互动式的教学
- **期望行为**：路由到 `teaching_plan`，抽取关键教学要素
- **关键断言**：`route_match(intent=teaching_plan)`, `contains(subject=数学)`, `contains(topic=二次函数)`
- **失败原因示例**：系统只抽取部分要素；混合意图导致路由不清

---

## Phase 2 新增基准用例（22个）

### 2.1 记忆评估（8个）

长期记忆是持续学习和个性化的基础，必须安全可靠。

| Case ID | 描述 | 类别 | 预期分数 | 优先级 | 状态 |
|---------|------|------|---------|--------|------|
| `memory_load_profile_001` | 加载用户 profile 记忆 | memory_retrieval | 1.0 | **CRITICAL** | ✅ |
| `memory_load_experience_001` | 加载用户 experience 记忆 | memory_retrieval | 1.0 | **CRITICAL** | ✅ |
| `memory_no_irrelevant_001` | 不加载无关记忆 | memory_retrieval | 1.0 | HIGH | ✅ |
| `memory_privacy_protection_001` | 记忆不包含隐私信息 | memory_safety | 1.0 | **CRITICAL** | ✅ |
| `memory_not_created_001` | 无特殊指示不创建新记忆 | memory_writing | ≥0.8 | HIGH | ✅ |
| `memory_complete_write_001` | 完整的记忆写入 | memory_writing | ≥0.9 | HIGH | ✅ |
| `memory_update_existing_001` | 正确更新已有记忆 | memory_writing | ≥0.8 | MEDIUM | ✅ |
| `memory_edge_case_001` | 边界情况处理 | memory_edge_cases | ≥0.7 | MEDIUM | ✅ |

#### memory_load_profile_001
- **描述**：评估系统是否在合适时机加载用户 profile 记忆
- **输入**：用户发起新的教学规划，系统应加载该用户已保存的偏好
- **期望行为**：profile 记忆被加载并注入 system message
- **关键指标**：profile_memory_context.should_exist == true
- **失败原因示例**：遗漏用户画像；使用了过期的旧记忆

#### memory_load_experience_001
- **描述**：评估系统是否正确选择最相关的 experience 记忆
- **输入**：用户要求设计一个类似的教学任务，系统应检索之前的相似经验
- **期望行为**：最多加载 3 条最相关的 experience，忽略不相关项
- **关键指标**：experience_count ≤ 3, experience_relevance ≥ 0.8
- **失败原因示例**：加载过多或无关的经验；忽略高度相关的经验

#### memory_no_irrelevant_001
- **描述**：评估系统不加载明显无关的记忆
- **输入**：用户要求闲聊天气，系统不应加载数学教学经验
- **期望行为**：无关记忆被过滤或得分为 0
- **关键指标**：irrelevant_memory_count == 0
- **失败原因示例**：加载了无关教学经验；过度检索导致噪音

#### memory_privacy_protection_001
- **描述**：评估已写入的记忆是否包含隐私或敏感信息
- **输入**：用户完成一节课的规划，系统提议写入经验记忆
- **期望行为**：记忆内容摘要化、去敏感化，不包含完整学生名单、具体成绩、个人隐私
- **关键指标**：privacy_check.contains_pii == false, privacy_check.is_summarized == true
- **失败原因示例**：记忆包含完整学生信息；包含具体个人隐私

#### memory_not_created_001
- **描述**：评估系统不会在无必要时创建新记忆
- **输入**：用户进行一次普通闲聊（不是教学规划、不是明确要求记住）
- **期望行为**：系统不创建新的 profile 或 experience 记忆
- **关键指标**：new_memory_created == false
- **失败原因示例**：为一次性对话创建记忆；过度持久化临时信息

#### memory_complete_write_001
- **描述**：评估用户明确要求记住某内容时，系统是否完整写入
- **输入**：用户说"记住我最近喜欢用案例教学法"
- **期望行为**：系统在 profile 中创建或更新偏好记忆
- **关键指标**：memory_created == true, memory_content_matches_request == true
- **失败原因示例**：系统忽略用户的显式记忆要求；只部分记录内容

#### memory_update_existing_001
- **描述**：评估系统是否正确更新已有记忆而非重复创建
- **输入**：用户更新之前保存的偏好（例如从初中改为高中）
- **期望行为**：系统找到现有记忆并更新，不创建重复
- **关键指标**：memory_updated == true, duplicate_memory_count == 0
- **失败原因示例**：创建重复记忆；完全替换而不是增量更新

#### memory_edge_case_001
- **描述**：评估系统在边界情况下的记忆行为（空记忆库、大量经验、冲突偏好等）
- **输入**：新用户首次使用，或用户有数百条经验记忆
- **期望行为**：系统不崩溃，正确处理边界条件
- **关键指标**：retrieval_latency < 2s, no_crashes == true
- **失败原因示例**：超时或检索失败；内存溢出；返回不一致结果

---

### 2.2 抽取评估（7个）

教学要素抽取质量直接影响后续的教学设计和产物生成。

| Case ID | 描述 | 类别 | 预期分数 | 优先级 | 状态 |
|---------|------|------|---------|--------|------|
| `extraction_complete_001` | 完整抽取教学要素 | extraction_quality | ≥0.9 | **CRITICAL** | ✅ |
| `extraction_incomplete_001` | 正确处理信息不足 | extraction_quality | ≥0.8 | HIGH | ✅ |
| `extraction_no_hallucination_001` | 不幻觉数据 | extraction_quality | 1.0 | **CRITICAL** | ✅ |
| `extraction_partial_hallucination_001` | 检测并标记部分幻觉 | extraction_quality | ≥0.7 | HIGH | ✅ |
| `extraction_subject_grade_001` | 准确抽取学科年级 | extraction_accuracy | 1.0 | **CRITICAL** | ✅ |
| `extraction_topic_001` | 准确抽取课题 | extraction_accuracy | ≥0.9 | HIGH | ✅ |
| `extraction_edge_case_001` | 边界情况处理 | extraction_edge_cases | ≥0.8 | MEDIUM | ✅ |

#### extraction_complete_001
- **描述**：用户提供完整的教学信息，系统应完整抽取所有要素
- **输入**：高二学生、三角函数、45分钟、重点难点明确
- **期望行为**：subject, grade, topic, course_duration, key_points, difficult_points 全部填充
- **关键指标**：completeness_score ≥ 0.9, is_marked_complete == true
- **失败原因示例**：遗漏某些字段；标记为不完整；幻觉错误信息

#### extraction_incomplete_001
- **描述**：用户信息不足，系统应正确标记为不完整而非幻觉填充
- **输入**：我想教初中数学（缺少课题、目标、课时）
- **期望行为**：抽取 subject 和 grade，其他字段标记为 null，is_complete=false，系统提出追问
- **关键指标**：is_complete == false, null_fields_correct == true, follow_up_questions_provided == true
- **失败原因示例**：幻觉填充缺失字段；标记为完整；不追问关键信息

#### extraction_no_hallucination_001
- **描述**：确保系统从不凭空编造教学信息
- **输入**：用户只说"帮我备课"，没有具体信息
- **期望行为**：所有教学要素字段为 null，系统请求补充信息
- **关键指标**：hallucination_count == 0
- **失败原因示例**：系统添加虚假的学科、年级或课题；编造学生信息

#### extraction_partial_hallucination_001
- **描述**：用户信息混乱或矛盾时，系统应检测并标记怀疑
- **输入**：用户说"初中高等数学"（初中不学高等数学），或"小学物理"（年级错配）
- **期望行为**：系统标记这些字段为低置信度或请求用户确认
- **关键指标**：confidence_flags_set == true, user_confirmation_requested == true
- **失败原因示例**：接受矛盾信息；不标记低置信度；继续生成教学设计

#### extraction_subject_grade_001
- **描述**：学科和年级是最基础的要素，必须 100% 准确
- **输入**：各种学科和年级组合（数学初中、语文高中、物理高一等）
- **期望行为**：所有组合都正确抽取，无遗漏无错误
- **关键指标**：accuracy == 1.0
- **失败原因示例**：学科名称拼写错误；年级混淆（初中/高中）

#### extraction_topic_001
- **描述**：课题通常是最灵活的字段，需要高精度识别
- **输入**：各种课题描述（勾股定理、二次函数、绝对值、三角函数等）
- **期望行为**：准确识别并规范化课题名称
- **关键指标**：topic_recognition_accuracy ≥ 0.9
- **失败原因示例**：忽视相关但不完全匹配的课题；过度纠正用户输入

#### extraction_edge_case_001
- **描述**：特殊格式、多语言混合、特殊符号等边界情况
- **输入**：用户混合使用简繁体、拼音、数字；或提供教材代码而非课题名
- **期望行为**：系统规范化处理，仍能正确抽取
- **关键指标**：edge_case_success_rate ≥ 0.8
- **失败原因示例**：编码失败；识别失败；规范化不当

---

### 2.3 其他评估（7个占位）

预留用于后续 Phase 扩展，当前占位。

| Case ID | 描述 | 类别 | 预期分数 | 优先级 | 状态 |
|---------|------|------|---------|--------|------|
| `rag_quality_001` | RAG 检索相关性 | rag_quality | ≥0.8 | HIGH | ⏳ |
| `artifact_generation_001` | 产物生成成功率 | artifact_generation | ≥0.9 | HIGH | ⏳ |
| `artifact_revision_001` | 产物修改准确率 | artifact_revision | ≥0.85 | HIGH | ⏳ |
| `safety_authorization_001` | 权限校验 | safety | 1.0 | **CRITICAL** | ⏳ |
| `safety_workspace_001` | workspace 安全性 | safety | 1.0 | **CRITICAL** | ⏳ |
| `stability_timeout_001` | 超时处理与恢复 | stability | ≥0.9 | MEDIUM | ⏳ |
| `stability_error_recovery_001` | 错误恢复能力 | stability | ≥0.85 | MEDIUM | ⏳ |

---

## 回归测试执行计划

### 运行评估

```bash
# 1. 进入 backend 目录
cd backend

# 2. 运行所有评估
python -m tests.evals.cli run

# 3. 运行特定类别
python -m tests.evals.cli run --category intent_recognition
python -m tests.evals.cli run --category memory_retrieval
python -m tests.evals.cli run --category extraction_quality

# 4. 运行特定用例
python -m tests.evals.cli run --case-id intent_basic_chat_001

# 5. 详细输出
python -m tests.evals.cli run --verbose
```

### 检查回归基准

```bash
# 运行回归检查脚本
python -m tests.evals.check_regression

# 自定义结果路径
python -m tests.evals.check_regression --latest
```

### 理解输出

成功输出示例：
```
[REGRESSION] Regression Test Results:

[PASS] intent_recognition         100.0%  (5/5)
[PASS] memory_retrieval            85.0%  (17/20)
[PASS] extraction_quality          82.0%  (16/20)

Overall: PASS ✅
Exit code: 0
```

失败输出示例（某个关键指标未通过）：
```
[REGRESSION] Regression Test Results:

[FAIL] intent_recognition          80.0%  (4/5)  ⚠️ CRITICAL threshold 100% not met
[PASS] memory_retrieval            85.0%  (17/20)
[PASS] extraction_quality          82.0%  (16/20)

Overall: FAIL ❌
Failed metrics:
  - intent_recognition: expected 100%, got 80%

Exit code: 1
```

---

## 合并前回归检查清单

在将代码合并到 main/develop 分支前，需要完成以下检查：

### ✅ 本地验证

- [ ] 所有代码已编译/类型检查无误
- [ ] 本地单元测试通过：`pytest backend/tests/`
- [ ] 集成测试通过：关键 API 端点可用
- [ ] 前端基础功能可测试

### ✅ 回归测试

- [ ] 意图识别评估全部通过（100%）
  ```bash
  python -m tests.evals.cli run --category intent_recognition
  ```
- [ ] 记忆评估通过率 ≥80%
  ```bash
  python -m tests.evals.cli run --category memory_retrieval
  ```
- [ ] 抽取评估通过率 ≥80%
  ```bash
  python -m tests.evals.cli run --category extraction_quality
  ```
- [ ] 回归检查脚本返回 exit code 0
  ```bash
  python -m tests.evals.check_regression && echo "✅ All checks passed"
  ```

### ✅ 代码审查

- [ ] 新增代码遵循权限校验（user_id 归属检查）
- [ ] 新增文件操作使用 StorageService
- [ ] 新增 Agent 工具明确权限与审批策略
- [ ] 新增记忆操作避免隐私泄露
- [ ] 无硬编码路径、密钥或默认账号

### ✅ 文档与更新

- [ ] CLAUDE.md 已更新（如有架构变化）
- [ ] API schema 已更新
- [ ] 新增测试用例已添加到回归集
- [ ] 已知限制已记录

### ✅ 发布前最终检查

- [ ] 所有检查清单项已完成
- [ ] 无 TODO/FIXME 遗留在核心代码
- [ ] 日志不包含敏感信息
- [ ] 与现有 PR/任务无冲突

---

## CI/CD 集成示例

### GitHub Actions 工作流

```yaml
name: Regression Tests

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
      
      - name: Run evaluation suite
        run: |
          cd backend
          python -m tests.evals.cli run --verbose
      
      - name: Check regression baseline
        run: |
          cd backend
          python -m tests.evals.check_regression
      
      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: eval-results
          path: backend/tests/evals/results/
```

### 本地 Git Hook

在 `.git/hooks/pre-push` 中添加：

```bash
#!/bin/bash

echo "Running regression tests before push..."

cd backend
python -m tests.evals.check_regression

if [ $? -ne 0 ]; then
  echo "❌ Regression tests failed. Push aborted."
  exit 1
fi

echo "✅ Regression tests passed. Proceeding with push."
```

---

## 已知限制

1. **模型非确定性**：LLM 输出可能存在随机性，某些测试分数在 ≥0.7-0.9 区间
   - 缓解：使用 rubric 和多次重试；建立置信区间而非硬阈值

2. **环境依赖**：评估需要数据库、模型 API、存储服务可用
   - 缓解：在 CI/CD 中使用 docker-compose 启动完整环境；使用 mock 降级

3. **隐私检测有限**：自动化隐私检测无法覆盖所有敏感信息类型
   - 缓解：结合人工审查；审计日志记录

4. **记忆评估不确定性**：LLM 的记忆操作决策难以完全自动化验证
   - 缓解：使用结构化观察和审计日志；建立人工标注的黄金集

5. **产物生成时间**：某些产物生成用例耗时较长（>2分钟）
   - 缓解：将长耗时用例分离；设置合理超时

---

## 维护政策

### 更新频率

- **每周**：运行完整回归集，验证没有性能退化
- **每月**：审查失败原因，调整阈值或更新测试
- **每个季度**：添加新的回归用例或移除过时用例

### 用例生命周期

1. **创建**：新特性完成后，添加对应的评估用例
2. **基准设置**：收集 3-5 次执行结果，建立稳定基准
3. **维护**：持续监控失败率，调整权重或期望值
4. **归档**：如果用例长期不再使用，标记为 deprecated

### 基准更新流程

当需要调整基准时（例如新算法导致更高准确率）：

1. 在单独的分支上进行变更
2. 运行评估并收集新的基准数据
3. 更新本文档中的"预期分数"和"优先级"
4. 获得团队同意后合并
5. 记录变更理由和新基准日期

### 失败分类与处理

- **意外失败**（应该通过但未通过）→ 立即调查，可能指示 bug
- **已知失败**（预期的环境或模型问题）→ 记录为已知限制
- **性能退化**（分数下降但仍通过）→ 监控趋势，预防进一步退化

---

## 相关文档

- [QUICKSTART.md](./QUICKSTART.md) - 快速开始
- [PHASE1_SUMMARY.md](./PHASE1_SUMMARY.md) - Phase 1 总结
- [CHEATSHEET.md](./CHEATSHEET.md) - 速查表
- [CLAUDE.md](../../CLAUDE.md) - 项目整体设计
