---
name: ppt-generator
description: 使用教学设计、文档摘要或主题信息生成可编辑的 PPT 相关产物。适用于制作课件、演示稿、16:9 播放型网页或导出 `.pptx` 文件。
compatibility: |
  Requires Node.js on the host. Exporting real `.pptx` files also requires `pptxgenjs`
  to already be available in the host environment or bundled by the application. Do not
  install dependencies at runtime with npm, pnpm, yarn, npx, pip, or shell package managers.
allowed-tools:
  - list_workspace_files
  - read_workspace_file
  - write_workspace_file
  - run_workspace_code
metadata:
  default-output: pptx
  preferred-runtime: node
---

# PPT Generator Skill

当用户要求“生成 PPT / 课件 / 幻灯片 / 可编辑演示稿”时加载本 skill。

这个 skill 的职责不是直接让模型裸写整份产物，而是指导 agent：

1. 先判断输出格式。
2. 再整理结构化内容。
3. 最后在 workspace 中生成并执行临时代码。

## 工作原则

- 先使用对话、教学设计方案、附件摘要作为主输入，不要凭空补事实。
- 先 `load_skill`，再按需读取 `references/` 中的提示模板。
- 需要新写代码时，只能使用 workspace 工具：
  `write_workspace_file`、`read_workspace_file`、`list_workspace_files`、`run_workspace_code`。
- 不要用 `shell` 运行 `python`、`node`、`npm`、`pip`。
- 不要在代码里安装依赖；依赖是否存在由宿主环境决定。
- 生成代码时优先写成单文件、可重复执行、带清晰注释的脚本。

## 输出格式路由

- 用户明确要 `.pptx`、PowerPoint、WPS 可编辑文件：走 `.pptx` 路径。
- 用户明确要网页演示或浏览器播放：走 HTML 路径。
- 用户没有说明格式：默认走 `.pptx` 路径。

## 推荐流程

### 1. 整理内容

- 从已有教学设计、用户消息、附件摘要里提炼出：
  主题、目标、页数预估、核心知识点、流程结构、需要强调的数据或案例。
- 如果是长文档或报告，先参考 `references/outline-prompt.md` 生成适合 8-12 页的提纲。

### 2. 选择参考资料

- HTML 可视化页面：阅读 `references/html-prompt.md`。
- SVG 单页视觉稿：阅读 `references/svg-prompt.md`。
- `.pptx` 脚本结构：阅读 `references/pptx-scaffold.md`。

只读取当前路径真正需要的参考文件，不要一次性加载全部资源。

### 3. 在 workspace 中写代码

- 先把提纲或结构化输入写入一个 JSON 或 Markdown 文件，便于脚本读取和复用。
- 再写主脚本，例如：
  - `generate_ppt.js` for `.pptx`
  - `generate_slides.js` or `generate_slides.py` for HTML
- 代码里应显式读取 `AGENT_WORKSPACE_ROOT`、`AGENT_OUTPUT_DIR` 这些环境变量，输出产物写到 `AGENT_OUTPUT_DIR`。

### 4. 执行代码

- Node.js 脚本用 `run_workspace_code(language="node", entrypoint="generate_ppt.js")`
- Python 脚本用 `run_workspace_code(language="python", entrypoint="generate_slides.py")`
- 执行后检查返回的：
  `exit_code`、`stdout`、`stderr`、`output_files`

如果失败：

- 先根据错误信息修正代码。
- 必要时读取刚写入的文件再迭代。
- 不要切换到 `shell` 重新跑同样的 Python / Node.js 逻辑。

## `.pptx` 路径要求

- 优先使用 Node.js。
- 如果宿主环境没有 `pptxgenjs`，明确说明是依赖缺失，不要尝试安装。
- 代码生成的最终文件应写入 `AGENT_OUTPUT_DIR`，文件名清晰，例如 `lesson-slides.pptx`。
- 页面比例默认 16:9。
- 结构默认包含：
  封面、目录/概览、核心知识页、活动设计页、总结页。

## HTML 路径要求

- 输出单文件 HTML 优先。
- 允许引用 CDN 资源，但不要在运行时依赖本地安装前端构建工具。
- 保持 16:9 演示友好，适配桌面展示。

## 失败处理

- 缺少依赖：直接说明缺少什么依赖，以及这属于宿主环境问题。
- 没有足够内容：先返回缺失信息，不要硬生成空洞内容。
- 执行超时：精简脚本，减少复杂逻辑后重试。

## 最终回复

- 简洁说明生成了什么。
- 如果有输出文件，指出关键 `output_files`。
- 如果失败，明确失败原因是：
  依赖缺失、代码错误、超时，还是输入信息不足。
