---
name: ppt-generator
description: 使用此 Skill 将任意文档、报告、主题内容转换为高质量的可视化 PPT 或网页展示。当用户想要制作 PPT、幻灯片、演示文稿、将报告/年报/财报转成可视化页面，或者提到"做PPT"、"生成PPT"、"转成幻灯片"、"可视化报告"、"演示文稿"、"直出pptx"等需求时，必须触发此 Skill。支持三种输出格式：① 可视化网页 HTML ② 浏览器可播放的 16:9 HTML ③ 直接导出 .pptx 文件（PowerPoint/WPS 可直接打开编辑）。采用卡片式布局 + Apple 发布会风格，视觉专业、信息清晰。
---

# PPT Generator Skill

将文档、报告或主题内容转化为专业可视化演示的完整工作流。

## 输出格式路由（优先判断）

拿到需求后，**首先判断输出格式**，再进入对应工作流：

| 用户说… | 输出格式 | 走哪条路 |
|--------|---------|---------|
| "做个网页/可视化报告" | HTML 滚动页 | Step 1 → 2 → **3A** |
| "做个PPT/幻灯片/可以播放" | HTML 16:9 | Step 1 → 2 → **3A** → **3B** |
| "导出pptx/直出ppt/要pptx文件/要能在PowerPoint里打开" | `.pptx` 文件 | Step 1 → 2 → **3C** |

**如果用户没有明确说明格式**，默认生成 `.pptx` 文件（最通用，可直接打开编辑）。

---

## Step 1：需求判断（快速）

- 内容来源：用户上传文件、URL、还是只给了主题？→ 若是主题，先网络搜索资料
- 品牌/主色调：能识别到品牌就自动用品牌色（小米橙 `#FF6900`、特斯拉红 `#CC0000`、华为红 `#CF0A2C` 等）
- 页数要求：未指定则根据内容量自动决定（通常 8-12 页）

若用户已提供完整内容，直接进入 Step 3。

---

## Step 2：内容提炼（长文档/财报场景）

输入是长篇报告时，先提炼再制作。提炼提示词：

```
请以专业分析师视角深度分析以下内容，提炼：
1. 核心结论与关键数据（重点标注数字、增长率、对比数据）
2. 主要亮点与风险
3. 结构化的章节划分建议（适合做成 8-12 页 PPT）
输出一份结构清晰、数据准确的分析报告，不少于 2000 字。
```

普通主题直接跳到 Step 3。

---

## Step 3A：生成 HTML 可视化网页

详细提示词见 `references/html-prompt.md`。

核心设计原则：
- Apple 发布会卡片式布局，纯黑背景 `#000000`，深灰卡片 `#1a1a1a`
- 自动识别品牌色作为高亮色
- 关键数字超大展示（`text-5xl/6xl`），中英双语副标题
- TailwindCSS + Chart.js + Font Awesome，全部 CDN，单文件输出
- Intersection Observer 滚动触发淡入动画

---

## Step 3B：HTML → 可播放 PPT 格式

在 3A 生成的 HTML 上追加：

```
请修改HTML文件，改成类似PPT的形式，每页16:9，键盘左右键/点击圆点可切换。放大文字以适配16:9页面尺寸。
```

浏览器 F11 全屏直接播放。

---

## Step 3C：直出 .pptx 文件 ⭐

**当用户需要 PowerPoint/WPS 可直接打开的 `.pptx` 文件时，走此路径。**

### 环境准备

```bash
npm list -g pptxgenjs || npm install -g pptxgenjs
```

### 设计系统（暗黑卡片风格）

所有 `.pptx` 生成脚本统一使用以下设计语言：

```javascript
// 颜色常量
const BG    = "000000";   // 页面背景
const CARD  = "1A1A1A";   // 卡片背景
const CARD2 = "222222";   // 次级卡片
const WHITE = "FFFFFF";
const GRAY1 = "AAAAAA";   // 正文辅助
const GRAY2 = "666666";   // 次要文字
const GRAY3 = "333333";   // 分隔线
const BORDER = "2A2A2A";  // 卡片边框
// BRAND 根据内容自动设置，例如小米: "FF6900"

// 复用 helpers（每个脚本都定义这几个函数）
const makeShadow = () => ({ type:"outer", blur:8, offset:2, angle:135, color:"000000", opacity:0.25 });

function addCard(slide, x, y, w, h, color=CARD) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color },
    line: { color: BORDER, width: 0.5 },
    shadow: makeShadow()
  });
}

function addAccentBar(slide, x, y, h) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 0.06, h,
    fill: { color: BRAND }, line: { color: BRAND }
  });
}

function addSectionLabel(slide, text, y=0.28) {
  slide.addText(text.toUpperCase(), {
    x:0.5, y, w:9, h:0.22,
    fontSize:8, color:BRAND, bold:true, charSpacing:4, margin:0
  });
}

function addSlideTitle(slide, zh, en, y=0.55) {
  slide.addText(zh, { x:0.5, y, w:9, h:0.55, fontSize:28, bold:true, color:WHITE, margin:0 });
  slide.addText(en, { x:0.5, y:y+0.52, w:9, h:0.22, fontSize:10, color:GRAY2, margin:0 });
}
```

### 幻灯片结构模板

每份 pptx 通常包含：

1. **封面**：大标题 + 品牌色 + 右侧核心数据卡片 3 个
2. **概览/矩阵页**：3 列等宽卡片，每张含大数字 + 说明
3. **技术/内容页（2×2）**：4 格卡片，每格图标圆圈 + 标题 + 正文
4. **数据对比页**：左侧表格卡 + 右侧 3 个数字卡
5. **图表页**：`slide.addChart()` 搭配数字摘要卡
6. **时间线页**：横向 5 节点时间轴 + 下方 3 个能力卡
7. **战略/详情页**：左侧英雄卡（大数字）+ 右侧内容卡
8. **总结页**：居中大标题 + 3 个图标卡

### 关键注意事项（避免踩坑）

```
❌ 颜色绝对不加 "#" 前缀 → color: "FF6900"  ✅
❌ shadow 不用 8 位 hex 表示透明度 → 用 opacity 属性  ✅
❌ 不复用同一个 shadow 对象 → 用 makeShadow() 每次新建  ✅
❌ 不用 unicode "•" 做列表 → 用 bullet: true  ✅
```

### 生成 & 输出流程

```bash
# 1. 写 Node.js 脚本到 /home/agent/ppt-output.js
# 2. 运行
node /home/agent/ppt-output.js
# 3. 复制到输出目录
cp /home/agent/*.pptx /mnt/user-data/outputs/
# 4. 视觉 QA（转 PDF → 图片 → 检查）
python3 /mnt/skills/public/pptx/scripts/office/soffice.py --headless --convert-to pdf output.pptx
pdftoppm -jpeg -r 150 output.pdf slide
# 5. present_files 给用户下载
```

完整 pptxgenjs API 参考见 `/mnt/skills/public/pptx/pptxgenjs.md`。

---

## 输出质量标准

✅ 卡片式布局，信息密度高不拥挤  
✅ 大数字优先，视觉冲击力强  
✅ 中英双语标题，设计感强  
✅ 品牌色自动识别  
✅ .pptx 可在 PowerPoint / WPS 直接打开编辑  
✅ HTML 版支持动画、响应式  

---

## 参考文件

- `references/html-prompt.md` — HTML 可视化完整提示词（Step 3A）
- `references/svg-prompt.md` — SVG 单页设计稿提示词
- `references/outline-prompt.md` — 大纲生成提示词（金字塔原理）
