const pptxgen = require("pptxgenjs");
const path = require("path");
const fs = require("fs");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "牛顿第一定律";

// =============================================
// 🎨 设计系统
// =============================================
const BG     = "1A1A2E";     // 深蓝色背景
const CARD   = "16213E";     // 卡片背景
const WHITE  = "FFFFFF";
const GRAY1  = "CCCCCC";
const GRAY2  = "888888";
const BRAND  = "E94560";     // 品牌红
const ACCENT = "0F3460";     // 辅助蓝

const makeShadow = () => ({ 
  type: "outer", blur: 6, offset: 2, angle: 135, color: "000000", opacity: 0.3 
});

// 卡片背景 + 边框 + 阴影
function addCard(slide, x, y, w, h, color = CARD) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color },
    line: { color: "0D1B2A", width: 0.5 },
    shadow: makeShadow()
  });
}

// 品牌色左侧细竖条
function addAccentBar(slide, x, y, h) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 0.08, h,
    fill: { color: BRAND },
    line: { color: BRAND }
  });
}

// 版块小标签
function addSectionLabel(slide, text, y = 0.28) {
  slide.addText(text.toUpperCase(), {
    x: 0.5, y, w: 9, h: 0.22,
    fontSize: 9, color: BRAND, bold: true, charSpacing: 3, margin: 0
  });
}

// 幻灯片主标题
function addSlideTitle(slide, zh, en = "", y = 0.55) {
  slide.addText(zh, {
    x: 0.5, y, w: 9, h: 0.55,
    fontSize: 28, bold: true, color: WHITE, margin: 0
  });
  if (en) {
    slide.addText(en, {
      x: 0.5, y: y + 0.52, w: 9, h: 0.22,
      fontSize: 10, color: GRAY2, margin: 0
    });
  }
}

// 图标圆圈
function addIconCircle(slide, icon, x, y, size = 0.45) {
  slide.addShape(pres.shapes.OVAL, {
    x, y, w: size, h: size,
    fill: { color: ACCENT },
    line: { color: BRAND, width: 0.5 }
  });
  slide.addText(icon, {
    x, y, w: size, h: size,
    fontSize: size * 18, align: "center", valign: "middle", margin: 0
  });
}

// =============================================
// 📑 幻灯片内容
// =============================================

// ---------- SLIDE 1: 封面 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };

  // 顶部标签
  s.addText("初三物理 · 实验探究", {
    x: 0.5, y: 0.38, w: 6, h: 0.2,
    fontSize: 8, color: GRAY2, charSpacing: 4, margin: 0
  });

  // 主标题
  s.addText([
    { text: "牛顿", options: { color: BRAND, bold: true } },
    { text: "第一定律", options: { color: WHITE, bold: true } }
  ], {
    x: 0.5, y: 0.85, w: 9, h: 1.0,
    fontSize: 52, margin: 0
  });

  s.addText("Newton's First Law", {
    x: 0.5, y: 2.6, w: 6, h: 0.3,
    fontSize: 14, color: GRAY1, margin: 0
  });

  // 分隔线
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 3.1, w: 1.5, h: 0.04,
    fill: { color: BRAND }, line: { color: BRAND }
  });

  // 底部信息卡
  const metas = [
    ["初三", "适用年级"],
    ["40分钟", "课时"],
    ["实验探究法", "教学方法"],
    ["斜面小车", "实验器材"]
  ];
  metas.forEach(([v, k], i) => {
    const bx = 0.5 + i * 2.35;
    addCard(s, bx, 3.4, 2.15, 0.85);
    s.addText(v, {
      x: bx, y: 3.45, w: 2.15, h: 0.4,
      fontSize: 18, bold: true, color: BRAND, align: "center", margin: 0
    });
    s.addText(k, {
      x: bx, y: 3.88, w: 2.15, h: 0.22,
      fontSize: 8, color: GRAY2, align: "center", margin: 0
    });
  });

  // 右侧实验提示
  addCard(s, 7.0, 0.6, 2.6, 2.5);
  addAccentBar(s, 7.0, 0.6, 2.5);
  s.addText("🔬 实验器材", {
    x: 7.15, y: 0.75, w: 2.3, h: 0.35,
    fontSize: 14, bold: true, color: WHITE, margin: 0
  });
  s.addText("斜面小车实验", {
    x: 7.15, y: 1.15, w: 2.3, h: 0.25,
    fontSize: 10, color: BRAND, margin: 0
  });
  s.addText("• 斜面轨道\n• 小车\n• 毛巾/棉布/木板\n• 刻度尺", {
    x: 7.15, y: 1.5, w: 2.3, h: 1.2,
    fontSize: 9, color: GRAY1, margin: 0
  });
}

// ---------- SLIDE 2: 学习目标 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Learning Objectives · 学习目标");
  addSlideTitle(s, "本节学习目标", "What you will learn today");

  const objectives = [
    { icon: "①", title: "知识与技能", sub: "Knowledge", 
      body: "理解牛顿第一定律的内容，掌握'一切'、'没有受到外力'、'总保持'等关键词的含义。" },
    { icon: "②", title: "过程与方法", sub: "Process & Methods", 
      body: "通过斜面小车实验，体验控制变量法和科学推理法在物理探究中的应用。" },
    { icon: "③", title: "情感态度", sub: "Attitude", 
      body: "培养敢于质疑、实事求是的科学态度，认识科学发展的曲折历程。" },
    { icon: "④", title: "实际应用", sub: "Application", 
      body: "能运用惯性知识解释生活中的实际现象，解决实际问题。" }
  ];

  objectives.forEach((obj, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const cx = 0.28 + col * 4.85, cy = 1.6 + row * 1.95, cw = 4.6, ch = 1.75;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    addIconCircle(s, obj.icon, cx + 0.2, cy + 0.22);
    s.addText(obj.title, {
      x: cx + 0.75, y: cy + 0.2, w: cw - 0.85, h: 0.32,
      fontSize: 14, bold: true, color: WHITE, margin: 0
    });
    s.addText(obj.sub, {
      x: cx + 0.75, y: cy + 0.52, w: cw - 0.85, h: 0.2,
      fontSize: 8, color: GRAY2, margin: 0
    });
    s.addText(obj.body, {
      x: cx + 0.2, y: cy + 0.85, w: cw - 0.3, h: 0.75,
      fontSize: 10, color: GRAY1, margin: 0
    });
  });
}

// ---------- SLIDE 3: 历史观点对比 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Historical Perspectives · 历史观点");
  addSlideTitle(s, "力与运动关系的探索", "From Aristotle to Galileo");

  // 亚里士多德观点（左）
  const leftX = 0.28, leftW = 4.6, leftH = 2.8;
  addCard(s, leftX, 1.55, leftW, leftH, "3D1A1A");
  s.addShape(pres.shapes.RECTANGLE, {
    x: leftX, y: 1.55, w: 0.08, h: leftH,
    fill: { color: "CC0000" }, line: { color: "CC0000" }
  });
  s.addText("❌ 亚里士多德", {
    x: leftX + 0.2, y: 1.7, w: leftW - 0.3, h: 0.35,
    fontSize: 16, bold: true, color: "FF6B6B", margin: 0
  });
  s.addText("Aristotle's View", {
    x: leftX + 0.2, y: 2.05, w: leftW - 0.3, h: 0.2,
    fontSize: 9, color: GRAY2, margin: 0
  });
  s.addText("观点：", {
    x: leftX + 0.2, y: 2.4, w: leftW - 0.3, h: 0.25,
    fontSize: 10, color: WHITE, margin: 0
  });
  s.addText("力是维持物体运动的原因", {
    x: leftX + 0.2, y: 2.65, w: leftW - 0.3, h: 0.3,
    fontSize: 14, bold: true, color: "FF6B6B", margin: 0
  });
  s.addText("直觉经验：\n• 推车才动，不推就停\n• 踢球才滚，不踢就停", {
    x: leftX + 0.2, y: 3.1, w: leftW - 0.3, h: 0.9,
    fontSize: 10, color: GRAY1, margin: 0
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: leftX + 0.2, y: 4.0, w: 1.2, h: 0.28,
    fill: { color: "3D1A1A" }, line: { color: "CC0000", width: 0.5 }, rectRadius: 0.05
  });
  s.addText("错误观点", {
    x: leftX + 0.2, y: 4.0, w: 1.2, h: 0.28,
    fontSize: 9, color: "FF6B6B", bold: true, align: "center", margin: 0
  });

  // 伽利略观点（右）
  const rightX = 5.12, rightW = 4.6, rightH = 2.8;
  addCard(s, rightX, 1.55, rightW, rightH, "0D3D2D");
  s.addShape(pres.shapes.RECTANGLE, {
    x: rightX, y: 1.55, w: 0.08, h: rightH,
    fill: { color: "2ECC71" }, line: { color: "2ECC71" }
  });
  s.addText("✓ 伽利略", {
    x: rightX + 0.2, y: 1.7, w: rightW - 0.3, h: 0.35,
    fontSize: 16, bold: true, color: "2ECC71", margin: 0
  });
  s.addText("Galileo's View", {
    x: rightX + 0.2, y: 2.05, w: rightW - 0.3, h: 0.2,
    fontSize: 9, color: GRAY2, margin: 0
  });
  s.addText("观点：", {
    x: rightX + 0.2, y: 2.4, w: rightW - 0.3, h: 0.25,
    fontSize: 10, color: WHITE, margin: 0
  });
  s.addText("力是改变物体运动状态的原因", {
    x: rightX + 0.2, y: 2.65, w: rightW - 0.3, h: 0.3,
    fontSize: 14, bold: true, color: "2ECC71", margin: 0
  });
  s.addText("科学推理：\n• 物体运动不需要力维持\n• 力改变运动状态", {
    x: rightX + 0.2, y: 3.1, w: rightW - 0.3, h: 0.9,
    fontSize: 10, color: GRAY1, margin: 0
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: rightX + 0.2, y: 4.0, w: 1.2, h: 0.28,
    fill: { color: "0D3D2D" }, line: { color: "2ECC71", width: 0.5 }, rectRadius: 0.05
  });
  s.addText("正确观点", {
    x: rightX + 0.2, y: 4.0, w: 1.2, h: 0.28,
    fontSize: 9, color: "2ECC71", bold: true, align: "center", margin: 0
  });

  // 底部引导
  addCard(s, 0.28, 4.55, 9.44, 0.85);
  s.addText("💡 科学启示：直觉经验不一定可靠，需要通过实验和推理来验证真理", {
    x: 0.5, y: 4.7, w: 9, h: 0.5,
    fontSize: 12, color: WHITE, align: "center", margin: 0
  });
}

// ---------- SLIDE 4: 实验探究步骤 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Experiment · 实验探究");
  addSlideTitle(s, "斜面小车实验", "Inclined Plane Experiment");

  // 实验步骤时间线
  addCard(s, 0.28, 1.5, 9.44, 1.6);
  const steps = [
    { num: "1", title: "准备器材", desc: "斜面、小车、\n毛巾/棉布/木板" },
    { num: "2", title: "控制变量", desc: "同一高度\n相同初速度" },
    { num: "3", title: "改变条件", desc: "不同表面\n观察距离" },
    { num: "4", title: "记录数据", desc: "滑行距离\n速度变化" },
    { num: "5", title: "科学推理", desc: "无阻力\n理想情况" }
  ];

  steps.forEach((step, i) => {
    const tx = 0.7 + i * 1.85;
    s.addShape(pres.shapes.OVAL, {
      x: tx - 0.15, y: 1.65, w: 0.3, h: 0.3,
      fill: { color: BRAND }, line: { color: BRAND }
    });
    s.addText(step.num, {
      x: tx - 0.15, y: 1.65, w: 0.3, h: 0.3,
      fontSize: 12, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0
    });
    if (i < steps.length - 1) {
      s.addShape(pres.shapes.RECTANGLE, {
        x: tx + 0.15, y: 1.78, w: 1.55, h: 0.03,
        fill: { color: "0F3460" }, line: { color: "0F3460" }
      });
    }
    s.addText(step.title, {
      x: tx - 0.5, y: 2.0, w: 1.3, h: 0.28,
      fontSize: 10, bold: true, color: WHITE, align: "center", margin: 0
    });
    s.addText(step.desc, {
      x: tx - 0.6, y: 2.3, w: 1.5, h: 0.6,
      fontSize: 8, color: GRAY1, align: "center", margin: 0
    });
  });

  // 实验结论表格
  addCard(s, 0.28, 3.25, 9.44, 2.15);
  s.addText("实验数据记录与分析", {
    x: 0.5, y: 3.4, w: 4, h: 0.25,
    fontSize: 11, bold: true, color: WHITE, margin: 0
  });

  // 表头
  const headers = ["表面材料", "阻力大小", "滑行距离", "速度减小快慢"];
  const colXs = [0.5, 2.5, 5.0, 7.5];
  headers.forEach((h, i) => {
    s.addText(h, {
      x: colXs[i], y: 3.75, w: 2, h: 0.3,
      fontSize: 10, bold: true, color: BRAND, margin: 0
    });
  });

  // 数据行
  const rows = [
    { material: "毛巾", resistance: "最大", distance: "最近", speed: "最快" },
    { material: "棉布", resistance: "较大", distance: "较近", speed: "较快" },
    { material: "木板", resistance: "最小", distance: "最远", speed: "最慢" },
    { material: "理想光滑", resistance: "为零", distance: "无限远", speed: "不变" }
  ];
  rows.forEach((row, i) => {
    const ry = 4.1 + i * 0.32;
    const highlight = i === 3;
    s.addText(row.material, {
      x: colXs[0], y: ry, w: 2, h: 0.28,
      fontSize: 9, color: highlight ? BRAND : GRAY1, bold: highlight, margin: 0
    });
    s.addText(row.resistance, {
      x: colXs[1], y: ry, w: 2, h: 0.28,
      fontSize: 9, color: highlight ? BRAND : GRAY1, bold: highlight, margin: 0
    });
    s.addText(row.distance, {
      x: colXs[2], y: ry, w: 2, h: 0.28,
      fontSize: 9, color: highlight ? BRAND : GRAY1, bold: highlight, margin: 0
    });
    s.addText(row.speed, {
      x: colXs[3], y: ry, w: 2, h: 0.28,
      fontSize: 9, color: highlight ? BRAND : GRAY1, bold: highlight, margin: 0
    });
  });
}

// ---------- SLIDE 5: 牛顿第一定律内容 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "The Law · 定律内容");
  addSlideTitle(s, "牛顿第一定律", "Newton's First Law of Motion");

  // 核心定律卡片
  const cardX = 0.28, cardY = 1.5, cardW = 9.44, cardH = 2.0;
  s.addShape(pres.shapes.RECTANGLE, {
    x: cardX, y: cardY, w: cardW, h: cardH,
    fill: { color: "1A0A20" },
    line: { color: BRAND, width: 1.5 },
    shadow: makeShadow()
  });
  addAccentBar(s, cardX, cardY, cardH);
  s.addText("📖 定律内容", {
    x: cardX + 0.25, y: cardY + 0.2, w: cardW - 0.4, h: 0.28,
    fontSize: 12, color: BRAND, charSpacing: 2, margin: 0
  });
  s.addText("一切物体在没有受到外力作用时，总保持静止状态或匀速直线运动状态。", {
    x: cardX + 0.25, y: cardY + 0.6, w: cardW - 0.4, h: 0.7,
    fontSize: 22, bold: true, color: WHITE, margin: 0
  });
  s.addText("An object at rest stays at rest, and an object in motion stays in motion at constant speed and in a straight line, unless acted upon by an unbalanced force.", {
    x: cardX + 0.25, y: cardY + 1.35, w: cardW - 0.4, h: 0.5,
    fontSize: 9, color: GRAY2, margin: 0
  });

  // 关键词解析
  s.addText("关键词解析", {
    x: 0.5, y: 3.7, w: 9, h: 0.28,
    fontSize: 12, bold: true, color: WHITE, margin: 0
  });

  const keywords = [
    { word: "一切物体", desc: "所有物体，无论大小、形态" },
    { word: "没有受到外力", desc: "理想化条件" },
    { word: "总保持", desc: "固有的、始终存在的性质" },
    { word: "静止或匀速直线", desc: "两种运动状态" }
  ];

  keywords.forEach((kw, i) => {
    const cx = 0.28 + i * 2.38, cy = 4.1, cw = 2.2, ch = 1.3;
    addCard(s, cx, cy, cw, ch);
    s.addText(kw.word, {
      x: cx + 0.15, y: cy + 0.15, w: cw - 0.25, h: 0.35,
      fontSize: 14, bold: true, color: BRAND, align: "center", margin: 0
    });
    s.addText(kw.desc, {
      x: cx + 0.15, y: cy + 0.55, w: cw - 0.25, h: 0.6,
      fontSize: 9, color: GRAY1, align: "center", margin: 0
    });
  });
}

// ---------- SLIDE 6: 惯性概念 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Inertia · 惯性概念");
  addSlideTitle(s, "惯性：物体的固有属性", "Understanding Inertia");

  // 定义卡片
  const cardX = 0.28, cardY = 1.5, cardW = 5.2, cardH = 2.3;
  addCard(s, cardX, cardY, cardW, cardH);
  addAccentBar(s, cardX, cardY, cardH);
  s.addText("📌 定义", {
    x: cardX + 0.2, y: cardY + 0.15, w: cardW - 0.3, h: 0.25,
    fontSize: 10, color: BRAND, charSpacing: 2, margin: 0
  });
  s.addText("物体保持运动状态不变的性质叫做惯性。", {
    x: cardX + 0.2, y: cardY + 0.5, w: cardW - 0.3, h: 0.6,
    fontSize: 14, bold: true, color: WHITE, margin: 0
  });
  s.addText("惯性是物体的固有属性，一切物体在任何情况下都具有惯性。", {
    x: cardX + 0.2, y: cardY + 1.15, w: cardW - 0.3, h: 0.5,
    fontSize: 10, color: GRAY1, margin: 0
  });

  // 关键要点
  s.addText("⚠️ 重点提示", {
    x: cardX + 0.2, y: cardY + 1.7, w: cardW - 0.3, h: 0.2,
    fontSize: 9, color: BRAND, margin: 0
  });
  s.addText("• 惯性大小只与质量有关\n• 与速度大小无关\n• 与受力情况无关", {
    x: cardX + 0.2, y: cardY + 1.95, w: cardW - 0.3, h: 0.75,
    fontSize: 9, color: GRAY1, margin: 0
  });

  // 右侧常见误区
  const rightX = 5.68, rightY = 1.5, rightW = 4.04, rightH = 2.3;
  addCard(s, rightX, rightY, rightW, rightH);
  addAccentBar(s, rightX, rightY, rightH);
  s.addText("❌ 常见误区纠正", {
    x: rightX + 0.2, y: rightY + 0.15, w: rightW - 0.3, h: 0.25,
    fontSize: 10, color: BRAND, margin: 0
  });

  const misconceptions = [
    { wrong: "物体运动越快惯性越大", right: "惯性只与质量有关" },
    { wrong: "静止的物体没有惯性", right: "任何状态都有惯性" },
    { wrong: "速度为0时惯性消失", right: "惯性始终存在" }
  ];

  misconceptions.forEach((m, i) => {
    s.addText("✗ " + m.wrong, {
      x: rightX + 0.2, y: rightY + 0.5 + i * 0.58, w: rightW - 0.3, h: 0.25,
      fontSize: 9, color: "FF6B6B", margin: 0
    });
    s.addText("✓ " + m.right, {
      x: rightX + 0.2, y: rightY + 0.75 + i * 0.58, w: rightW - 0.3, h: 0.25,
      fontSize: 9, color: "2ECC71", margin: 0
    });
  });

  // 底部图示
  s.addText("生活实例", {
    x: 0.5, y: 4.0, w: 9, h: 0.25,
    fontSize: 11, bold: true, color: WHITE, margin: 0
  });

  const examples = [
    { icon: "🚗", title: "汽车刹车", desc: "人向前倾" },
    { icon: "🔨", title: "锤头松动", desc: "撞击锤柄紧固" },
    { icon: "🏃", title: "跳远助跑", desc: "利用惯性" },
    { icon: "🧹", title: "抖动衣服", desc: "灰尘脱落" }
  ];

  examples.forEach((ex, i) => {
    const cx = 0.28 + i * 2.38, cy = 4.35, cw = 2.2, ch = 1.05;
    addCard(s, cx, cy, cw, ch);
    s.addText(ex.icon, {
      x: cx, y: cy + 0.08, w: cw, h: 0.35,
      fontSize: 20, align: "center", margin: 0
    });
    s.addText(ex.title, {
      x: cx + 0.1, y: cy + 0.45, w: cw - 0.2, h: 0.25,
      fontSize: 10, bold: true, color: WHITE, align: "center", margin: 0
    });
    s.addText(ex.desc, {
      x: cx + 0.1, y: cy + 0.72, w: cw - 0.2, h: 0.22,
      fontSize: 8, color: GRAY1, align: "center", margin: 0
    });
  });
}

// ---------- SLIDE 7: 惯性应用案例 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Application · 实际应用");
  addSlideTitle(s, "惯性现象解释方法", "Three-Step Analysis Method");

  // 三步法
  addCard(s, 0.28, 1.5, 9.44, 1.3);
  s.addText("惯性现象分析三步法", {
    x: 0.5, y: 1.6, w: 9, h: 0.25,
    fontSize: 11, bold: true, color: WHITE, margin: 0
  });

  const steps2 = [
    { num: "1", text: "确认物体原来的运动状态" },
    { num: "2", text: "分析哪个物体受力改变了运动状态" },
    { num: "3", text: "判断另一物体由于惯性保持原状态" }
  ];

  steps2.forEach((step, i) => {
    const sx = 0.5 + i * 3.15;
    s.addShape(pres.shapes.OVAL, {
      x: sx, y: 2.0, w: 0.35, h: 0.35,
      fill: { color: BRAND }, line: { color: BRAND }
    });
    s.addText(step.num, {
      x: sx, y: 2.0, w: 0.35, h: 0.35,
      fontSize: 14, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0
    });
    s.addText(step.text, {
      x: sx + 0.45, y: 2.0, w: 2.6, h: 0.5,
      fontSize: 10, color: GRAY1, margin: 0
    });
  });

  // 案例分析
  const cases = [
    {
      title: "案例1：锤头松动",
      question: "为什么把锤柄在地上撞击几下，锤头就紧了？",
      answer: "锤柄撞击地面时停止运动，锤头由于惯性继续向下运动，从而套紧在锤柄上。"
    },
    {
      title: "案例2：跳远助跑",
      question: "为什么跳远运动员要助跑？",
      answer: "助跑使运动员获得水平速度，起跳后由于惯性保持向前的运动，跳得更远。"
    },
    {
      title: "案例3：汽车安全带",
      question: "为什么汽车要系安全带？",
      answer: "急刹车时人由于惯性继续向前运动，安全带防止人向前撞击造成伤害。"
    }
  ];

  cases.forEach((c, i) => {
    const cx = 0.28 + i * 3.22, cy = 3.0, cw = 3.05, ch = 2.35;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    s.addText(c.title, {
      x: cx + 0.15, y: cy + 0.15, w: cw - 0.25, h: 0.28,
      fontSize: 11, bold: true, color: BRAND, margin: 0
    });
    s.addText(c.question, {
      x: cx + 0.15, y: cy + 0.5, w: cw - 0.25, h: 0.6,
      fontSize: 9, color: WHITE, margin: 0
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx + 0.15, y: cy + 1.15, w: 0.6, h: 0.03,
      fill: { color: BRAND }, line: { color: BRAND }
    });
    s.addText("答案：", {
      x: cx + 0.15, y: cy + 1.25, w: cw - 0.25, h: 0.22,
      fontSize: 8, color: BRAND, margin: 0
    });
    s.addText(c.answer, {
      x: cx + 0.15, y: cy + 1.5, w: cw - 0.25, h: 0.75,
      fontSize: 8, color: GRAY1, margin: 0
    });
  });
}

// ---------- SLIDE 8: 课堂小结 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addText("SUMMARY", {
    x: 0.5, y: 0.5, w: 9, h: 0.22,
    fontSize: 9, color: BRAND, bold: true, charSpacing: 4, align: "center", margin: 0
  });

  s.addText([
    { text: "牛顿", options: { color: WHITE } },
    { text: "第一定律", options: { color: BRAND } }
  ], {
    x: 0.5, y: 0.85, w: 9, h: 0.65,
    fontSize: 42, bold: true, align: "center", margin: 0
  });

  s.addText("课堂小结", {
    x: 0.5, y: 1.55, w: 9, h: 0.4,
    fontSize: 28, bold: true, color: WHITE, align: "center", margin: 0
  });
  s.addText("Law of Inertia · Key Takeaways", {
    x: 0.5, y: 2.0, w: 9, h: 0.22,
    fontSize: 10, color: GRAY2, align: "center", margin: 0
  });

  // 三个要点卡片
  const summaries = [
    { icon: "📐", title: "定律内容", desc: "一切物体在没有受到外力时，总保持静止或匀速直线运动状态" },
    { icon: "🔬", title: "实验方法", desc: "斜面小车实验 + 科学推理法（理想实验法）" },
    { icon: "💡", title: "惯性理解", desc: "物体固有的属性，只与质量有关，与速度、受力无关" }
  ];

  summaries.forEach((sum, i) => {
    const cx = 0.65 + i * 3.15, cy = 2.5, cw = 2.9, ch = 2.0;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    s.addText(sum.icon, {
      x: cx, y: cy + 0.2, w: cw, h: 0.5,
      fontSize: 28, align: "center", margin: 0
    });
    s.addText(sum.title, {
      x: cx + 0.1, y: cy + 0.75, w: cw - 0.2, h: 0.35,
      fontSize: 14, bold: true, color: WHITE, align: "center", margin: 0
    });
    s.addText(sum.desc, {
      x: cx + 0.1, y: cy + 1.15, w: cw - 0.2, h: 0.7,
      fontSize: 9, color: GRAY1, align: "center", margin: 0
    });
  });

  // 底部思考题
  addCard(s, 0.28, 4.65, 9.44, 0.85);
  s.addText("🤔 课后思考：如果物体受力平衡，它会保持什么状态？（为下节课'二力平衡'做铺垫）", {
    x: 0.5, y: 4.8, w: 9, h: 0.55,
    fontSize: 11, color: WHITE, align: "center", margin: 0
  });
}

// =============================================
// 💾 输出文件
// =============================================
const outputDir = process.env.AGENT_OUTPUT_DIR || ".";
const outputPath = path.join(outputDir, "牛顿第一定律-教学课件.pptx");

pres.writeFile({ fileName: outputPath })
  .then(() => {
    console.log("✅ 生成成功:", outputPath);
    // 列出生成的文件
    if (fs.existsSync(outputPath)) {
      const stats = fs.statSync(outputPath);
      console.log("📊 文件大小:", (stats.size / 1024).toFixed(2), "KB");
    }
  })
  .catch(e => {
    console.error("❌ 错误:", e);
    process.exit(1);
  });