const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "牛顿第一定律";
pres.author = "物理课件";

// =============================================
// 🎨 设计系统 - 教育风格（深蓝/白色调）
// =============================================
const BG = "0A1628";        // 深蓝背景
const CARD = "152238";      // 卡片背景
const CARD2 = "1E2F4A";     // 次要卡片
const WHITE = "FFFFFF";
const GRAY1 = "CCCCCC";
const GRAY2 = "999999";
const GRAY3 = "555555";
const BORDER = "2A3F5F";
const BRAND = "4DA6FF";     // 科技蓝
const BRAND_DIM = "0D2840"; // 品牌色暗化版
const ACCENT = "FF9F43";    // 橙色强调色

const makeShadow = () => ({ type: "outer", blur: 8, offset: 2, angle: 135, color: "000000", opacity: 0.3 });

function addCard(slide, x, y, w, h, color = CARD) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color },
    line: { color: BORDER, width: 0.5 },
    shadow: makeShadow()
  });
}

function addAccentBar(slide, x, y, h) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 0.08, h,
    fill: { color: BRAND }, line: { color: BRAND }
  });
}

function addSectionLabel(slide, text, y = 0.3) {
  slide.addText(text.toUpperCase(), {
    x: 0.5, y, w: 9, h: 0.2, fontSize: 8, color: BRAND, bold: true, charSpacing: 3, margin: 0
  });
}

function addSlideTitle(slide, zh, en, y = 0.6) {
  slide.addText(zh, { x: 0.5, y, w: 9, h: 0.5, fontSize: 26, bold: true, color: WHITE, margin: 0 });
  slide.addText(en, { x: 0.5, y: y + 0.45, w: 9, h: 0.2, fontSize: 9, color: GRAY2, margin: 0 });
}

function addIconCircle(slide, icon, x, y, size = 0.5) {
  slide.addShape(pres.shapes.OVAL, {
    x, y, w: size, h: size,
    fill: { color: BRAND_DIM }, line: { color: BRAND, width: 0.5 }
  });
  slide.addText(icon, { x, y, w: size, h: size, fontSize: size * 20, align: "center", valign: "middle", margin: 0 });
}

// =============================================
// 📑 幻灯片内容
// =============================================

// ---------- SLIDE 1: 封面 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };

  // 顶部标签
  s.addText("物理 · 九年级 · 牛顿第一定律", { x: 0.5, y: 0.4, w: 6, h: 0.2, fontSize: 8, color: GRAY2, charSpacing: 3, margin: 0 });

  // 主标题
  s.addText([
    { text: "牛顿", options: { color: BRAND, bold: true } },
    { text: "第一定律", options: { color: WHITE, bold: true } }
  ], { x: 0.5, y: 1.2, w: 7, h: 1.0, fontSize: 48, margin: 0 });

  s.addText("力与运动的关系", { x: 0.5, y: 2.4, w: 6, h: 0.4, fontSize: 16, color: GRAY1, margin: 0 });

  // 分隔线
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 2.95, w: 1.5, h: 0.06, fill: { color: BRAND }, line: { color: BRAND } });

  // 底部信息
  s.addText("授课人：XXX", { x: 0.5, y: 3.3, w: 3, h: 0.25, fontSize: 11, color: GRAY2, margin: 0 });
  s.addText("课时：40 分钟", { x: 4, y: 3.3, w: 3, h: 0.25, fontSize: 11, color: GRAY2, margin: 0 });

  // 右侧装饰
  addCard(s, 7.0, 0.8, 2.6, 2.0, CARD2);
  addAccentBar(s, 7.0, 0.8, 2.0);
  s.addText("🔬", { x: 7.3, y: 1.0, w: 0.5, h: 0.5, fontSize: 32, align: "center", margin: 0 });
  s.addText("物理探索", { x: 7.9, y: 1.1, w: 1.5, h: 0.3, fontSize: 14, bold: true, color: WHITE, margin: 0 });
  s.addText("Science & Physics", { x: 7.9, y: 1.45, w: 1.5, h: 0.2, fontSize: 8, color: GRAY2, margin: 0 });
  s.addText("牛顿第一定律是经典力学的基石", { x: 7.1, y: 1.9, w: 2.4, h: 0.6, fontSize: 9, color: GRAY1, margin: 0 });
}

// ---------- SLIDE 2: 学习目标 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Learning Objectives");
  addSlideTitle(s, "学习目标", "What We Will Learn Today");

  const objectives = [
    { icon: "①", title: "知道牛顿第一定律内容", desc: "能够准确表述牛顿第一定律的完整内容，理解关键词含义。" },
    { icon: "②", title: "理解惯性概念", desc: "掌握惯性的定义，知道惯性是物体固有的属性，只与质量有关。" },
    { icon: "③", title: "会用惯性解释现象", desc: "能够运用惯性知识解释生活中的常见现象，如急刹车、拍打衣服等。" }
  ];

  objectives.forEach((obj, i) => {
    const cx = 0.5, cy = 1.8 + i * 1.15, cw = 9.0, ch = 1.0;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    addIconCircle(s, obj.icon, cx + 0.2, cy + 0.25, 0.45);
    s.addText(obj.title, { x: cx + 0.75, y: cy + 0.22, w: cw - 1.0, h: 0.35, fontSize: 14, bold: true, color: WHITE, margin: 0 });
    s.addText(obj.desc, { x: cx + 0.75, y: cy + 0.58, w: cw - 1.0, h: 0.35, fontSize: 9, color: GRAY1, margin: 0 });
  });
}

// ---------- SLIDE 3: 情境思考 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Think About It");
  addSlideTitle(s, "情境思考：运动需要力来维持吗？", "Does Motion Require Force to Continue?");

  // 左侧问题卡
  addCard(s, 0.5, 1.7, 4.5, 2.8);
  s.addText("生活现象", { x: 0.7, y: 1.85, w: 4.1, h: 0.25, fontSize: 10, color: BRAND, bold: true, margin: 0 });
  s.addText("推箱子 → 动", { x: 0.7, y: 2.2, w: 4.1, h: 0.35, fontSize: 16, bold: true, color: WHITE, margin: 0 });
  s.addText("不推 → 停", { x: 0.7, y: 2.6, w: 4.1, h: 0.35, fontSize: 16, bold: true, color: WHITE, margin: 0 });

  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 3.1, w: 4.1, h: 0.03, fill: { color: GRAY3 }, line: { color: GRAY3 } });

  s.addText("亚里士多德的观点：", { x: 0.7, y: 3.3, w: 4.1, h: 0.25, fontSize: 11, color: GRAY2, margin: 0 });
  s.addText("力是维持物体运动的原因", { x: 0.7, y: 3.55, w: 4.1, h: 0.35, fontSize: 13, color: ACCENT, bold: true, margin: 0 });
  s.addText("这个观点对吗？", { x: 0.7, y: 3.95, w: 4.1, h: 0.4, fontSize: 14, color: BRAND, bold: true, margin: 0 });

  // 右侧互动区
  addCard(s, 5.3, 1.7, 4.3, 1.3, CARD2);
  addAccentBar(s, 5.3, 1.7, 1.3);
  s.addText("互动投票", { x: 5.5, y: 1.85, w: 3.9, h: 0.25, fontSize: 10, color: BRAND, bold: true, margin: 0 });
  s.addText("你认为亚里士多德的观点正确吗？", { x: 5.5, y: 2.2, w: 3.9, h: 0.35, fontSize: 11, color: WHITE, margin: 0 });
  s.addText("✅ 对   ❌ 错", { x: 5.5, y: 2.65, w: 3.9, h: 0.3, fontSize: 14, bold: true, color: GRAY1, margin: 0 });

  addCard(s, 5.3, 3.2, 4.3, 1.3, CARD2);
  addAccentBar(s, 5.3, 3.2, 1.3);
  s.addText("思考提示", { x: 5.5, y: 3.35, w: 3.9, h: 0.25, fontSize: 10, color: BRAND, bold: true, margin: 0 });
  s.addText("如果表面绝对光滑，物体会停下来吗？", { x: 5.5, y: 3.7, w: 3.9, h: 0.65, fontSize: 11, color: GRAY1, margin: 0 });
}

// ---------- SLIDE 4: 历史回顾：伽利略 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "History");
  addSlideTitle(s, "历史回顾：伽利略的理想实验", "Galileo's Thought Experiment");

  // 左侧伽利略信息
  addCard(s, 0.5, 1.7, 4.0, 3.0);
  addAccentBar(s, 0.5, 1.7, 3.0);
  s.addText("伽利略·伽利雷", { x: 0.7, y: 1.85, w: 3.6, h: 0.35, fontSize: 16, bold: true, color: WHITE, margin: 0 });
  s.addText("Galileo Galilei (1564-1642)", { x: 0.7, y: 2.25, w: 3.6, h: 0.2, fontSize: 8, color: GRAY2, margin: 0 });

  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 2.55, w: 3.6, h: 0.03, fill: { color: GRAY3 }, line: { color: GRAY3 } });

  s.addText("🔬 意大利物理学家、天文学家", { x: 0.7, y: 2.75, w: 3.6, h: 0.25, fontSize: 10, color: GRAY1, margin: 0 });
  s.addText("📚 近代科学方法的奠基人", { x: 0.7, y: 3.05, w: 3.6, h: 0.25, fontSize: 10, color: GRAY1, margin: 0 });
  s.addText("💡 首次提出：力不是维持物体运动的原因", { x: 0.7, y: 3.35, w: 3.6, h: 0.25, fontSize: 10, color: BRAND, bold: true, margin: 0 });

  // 右侧斜面实验示意图
  addCard(s, 4.8, 1.7, 4.8, 3.0, CARD2);
  addAccentBar(s, 4.8, 1.7, 3.0);
  s.addText("斜面实验", { x: 5.0, y: 1.85, w: 4.4, h: 0.25, fontSize: 10, color: BRAND, bold: true, margin: 0 });

  // 简单图示 - 使用矩形替代三角形
  s.addShape(pres.shapes.RECTANGLE, { x: 5.2, y: 2.3, w: 0.1, h: 1.0, fill: { color: GRAY3 }, line: { color: GRAY2 } });
  s.addShape(pres.shapes.RECTANGLE, { x: 5.2, y: 3.2, w: 1.5, h: 0.1, fill: { color: GRAY3 }, line: { color: GRAY2 } });
  s.addShape(pres.shapes.RECTANGLE, { x: 6.7, y: 2.7, w: 2.5, h: 0.08, fill: { color: GRAY2 }, line: { color: GRAY2 } });
  s.addShape(pres.shapes.OVAL, { x: 6.5, y: 2.65, w: 0.25, h: 0.25, fill: { color: BRAND }, line: { color: BRAND } });

  s.addText("小车从斜面滑下", { x: 5.0, y: 3.5, w: 4.4, h: 0.25, fontSize: 9, color: GRAY1, margin: 0 });
  s.addText("观察在不同表面上的滑行距离", { x: 5.0, y: 3.8, w: 4.4, h: 0.25, fontSize: 9, color: GRAY1, margin: 0 });
  s.addText("👉 阻力越小，滑行越远", { x: 5.0, y: 4.1, w: 4.4, h: 0.35, fontSize: 11, color: ACCENT, bold: true, margin: 0 });
}

// ---------- SLIDE 5: 实验推理（关键页）----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Key Concept");
  addSlideTitle(s, "实验推理：理想实验方法", "Experimental Reasoning: Ideal Experiment");

  // 实验现象
  addCard(s, 0.5, 1.7, 4.3, 1.8);
  addAccentBar(s, 0.5, 1.7, 1.8);
  s.addText("实验现象", { x: 0.7, y: 1.85, w: 3.9, h: 0.25, fontSize: 10, color: BRAND, bold: true, margin: 0 });

  const surfaces = [
    { name: "毛巾表面", distance: "短", color: "8B4513" },
    { name: "棉布表面", distance: "中", color: "A0A0A0" },
    { name: "木板表面", distance: "长", color: "DEB887" }
  ];

  surfaces.forEach((surf, i) => {
    const sy = 2.2 + i * 0.4;
    s.addText(surf.name, { x: 0.7, y: sy, w: 2.0, h: 0.3, fontSize: 9, color: GRAY1, margin: 0 });
    s.addShape(pres.shapes.RECTANGLE, { x: 2.8, y: sy + 0.1, w: 1.8, h: 0.12, fill: { color: surf.color }, line: { color: surf.color } });
    s.addText(surf.distance, { x: 4.0, y: sy, w: 0.5, h: 0.3, fontSize: 9, color: GRAY2, margin: 0 });
  });

  s.addText("结论：阻力越小，滑行越远", { x: 0.7, y: 3.1, w: 3.9, h: 0.3, fontSize: 10, color: ACCENT, bold: true, margin: 0 });

  // 逻辑推理
  addCard(s, 5.1, 1.7, 4.5, 1.8, CARD2);
  addAccentBar(s, 5.1, 1.7, 1.8);
  s.addText("逻辑推理", { x: 5.3, y: 1.85, w: 4.1, h: 0.25, fontSize: 10, color: BRAND, bold: true, margin: 0 });

  s.addText("若阻力为零 → ?", { x: 5.3, y: 2.2, w: 4.1, h: 0.35, fontSize: 13, color: WHITE, margin: 0 });
  s.addShape(pres.shapes.RECTANGLE, { x: 5.3, y: 2.6, w: 4.1, h: 0.03, fill: { color: GRAY3 }, line: { color: GRAY3 } });
  s.addText("小车将永远运动下去！", { x: 5.3, y: 2.8, w: 4.1, h: 0.4, fontSize: 14, color: BRAND, bold: true, margin: 0 });
  s.addText("不会停下来", { x: 5.3, y: 3.2, w: 4.1, h: 0.25, fontSize: 10, color: GRAY1, margin: 0 });

  // 方法总结
  addCard(s, 0.5, 3.7, 9.1, 1.3, CARD2);
  addAccentBar(s, 0.5, 3.7, 1.3);
  s.addText("科学方法：理想实验", { x: 0.7, y: 3.85, w: 8.7, h: 0.3, fontSize: 12, bold: true, color: WHITE, margin: 0 });
  s.addText("实验 + 推理 = 理想实验方法", { x: 0.7, y: 4.2, w: 4.0, h: 0.35, fontSize: 11, color: GRAY1, margin: 0 });
  s.addText("🔑 这是物理学中重要的科学研究方法", { x: 5.0, y: 4.2, w: 4.0, h: 0.35, fontSize: 11, color: BRAND, bold: true, margin: 0 });
}

// ---------- SLIDE 6: 牛顿第一定律 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Newton's First Law");
  addSlideTitle(s, "牛顿第一定律", "Newton's First Law of Motion");

  // 定律内容
  addCard(s, 0.5, 1.7, 9.1, 2.2, CARD2);
  addAccentBar(s, 0.5, 1.7, 2.2);

  s.addText("定律内容", { x: 0.7, y: 1.85, w: 8.7, h: 0.3, fontSize: 11, color: BRAND, bold: true, margin: 0 });

  s.addText("一切物体在没有受到力的作用时，", { x: 0.7, y: 2.25, w: 8.7, h: 0.45, fontSize: 16, color: WHITE, margin: 0 });
  s.addText("总保持静止状态或匀速直线运动状态。", { x: 0.7, y: 2.75, w: 8.7, h: 0.45, fontSize: 16, color: WHITE, margin: 0 });

  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 3.35, w: 8.7, h: 0.03, fill: { color: GRAY3 }, line: { color: GRAY3 } });

  // 关键词高亮
  s.addText("关键词解读：", { x: 0.7, y: 3.5, w: 8.7, h: 0.25, fontSize: 10, color: GRAY2, margin: 0 });
  s.addText("【一切】", { x: 0.7, y: 3.75, w: 1.0, h: 0.25, fontSize: 10, color: ACCENT, bold: true, margin: 0 });
  s.addText("指所有物体，无一例外", { x: 1.8, y: 3.75, w: 2.5, h: 0.25, fontSize: 9, color: GRAY1, margin: 0 });
  s.addText("【总】", { x: 4.5, y: 3.75, w: 0.8, h: 0.25, fontSize: 10, color: ACCENT, bold: true, margin: 0 });
  s.addText("始终如此，不会改变", { x: 5.4, y: 3.75, w: 2.5, h: 0.25, fontSize: 9, color: GRAY1, margin: 0 });
  s.addText("【或】", { x: 8.0, y: 3.75, w: 0.8, h: 0.25, fontSize: 10, color: ACCENT, bold: true, margin: 0 });
  s.addText("两种状态必居其一", { x: 8.9, y: 3.75, w: 2.0, h: 0.25, fontSize: 9, color: GRAY1, margin: 0 });

  // 图示
  addCard(s, 0.5, 4.1, 4.3, 1.2);
  s.addText("🛑 静止状态", { x: 0.7, y: 4.25, w: 3.9, h: 0.4, fontSize: 12, bold: true, color: WHITE, align: "center", margin: 0 });
  s.addText("物体保持静止", { x: 0.7, y: 4.7, w: 3.9, h: 0.25, fontSize: 9, color: GRAY1, align: "center", margin: 0 });

  addCard(s, 5.3, 4.1, 4.3, 1.2);
  s.addText("➡️ 匀速直线运动状态", { x: 5.5, y: 4.25, w: 3.9, h: 0.4, fontSize: 12, bold: true, color: WHITE, align: "center", margin: 0 });
  s.addText("速度大小方向都不变", { x: 5.5, y: 4.7, w: 3.9, h: 0.25, fontSize: 9, color: GRAY1, align: "center", margin: 0 });
}

// ---------- SLIDE 7: 力与运动的关系 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Force and Motion");
  addSlideTitle(s, "力与运动的关系", "Understanding Force and Motion");

  // 错误观念
  addCard(s, 0.5, 1.7, 4.3, 2.8, CARD);
  addAccentBar(s, 0.5, 1.7, 2.8);
  s.addText("❌ 错误观念", { x: 0.7, y: 1.85, w: 3.9, h: 0.3, fontSize: 12, bold: true, color: "FF4757", margin: 0 });
  s.addText("力是维持物体运动的原因", { x: 0.7, y: 2.3, w: 3.9, h: 0.5, fontSize: 15, color: GRAY1, margin: 0 });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 2.9, w: 3.9, h: 0.03, fill: { color: "FF4757" }, line: { color: "FF4757" } });
  s.addText("这是亚里士多德的观点", { x: 0.7, y: 3.1, w: 3.9, h: 0.25, fontSize: 9, color: GRAY2, margin: 0 });
  s.addText("已被伽利略和牛顿推翻", { x: 0.7, y: 3.4, w: 3.9, h: 0.25, fontSize: 9, color: GRAY2, margin: 0 });
  s.addText("生活中'推则动，不推则停'的现象是因为存在摩擦力", { x: 0.7, y: 3.75, w: 3.9, h: 0.5, fontSize: 8, color: GRAY1, margin: 0 });

  // 正确观念
  addCard(s, 5.3, 1.7, 4.3, 2.8, CARD2);
  addAccentBar(s, 5.3, 1.7, 2.8);
  s.addText("✅ 正确观念", { x: 5.5, y: 1.85, w: 3.9, h: 0.3, fontSize: 12, bold: true, color: BRAND, margin: 0 });
  s.addText("力是改变物体运动状态的原因", { x: 5.5, y: 2.3, w: 3.9, h: 0.5, fontSize: 15, color: WHITE, margin: 0 });
  s.addShape(pres.shapes.RECTANGLE, { x: 5.5, y: 2.9, w: 3.9, h: 0.03, fill: { color: BRAND }, line: { color: BRAND } });
  s.addText("这是牛顿第一定律的核心", { x: 5.5, y: 3.1, w: 3.9, h: 0.25, fontSize: 9, color: GRAY2, margin: 0 });
  s.addText("力的作用效果：", { x: 5.5, y: 3.4, w: 3.9, h: 0.25, fontSize: 9, color: GRAY1, margin: 0 });
  s.addText("• 使静止物体开始运动", { x: 5.5, y: 3.7, w: 3.9, h: 0.25, fontSize: 8, color: GRAY1, margin: 0 });
  s.addText("• 使运动物体加速或减速", { x: 5.5, y: 3.95, w: 3.9, h: 0.25, fontSize: 8, color: GRAY1, margin: 0 });
  s.addText("• 改变物体运动方向", { x: 5.5, y: 4.2, w: 3.9, h: 0.25, fontSize: 8, color: GRAY1, margin: 0 });
}

// ---------- SLIDE 8: 惯性概念 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Inertia");
  addSlideTitle(s, "惯性概念", "Understanding Inertia");

  // 定义
  addCard(s, 0.5, 1.7, 9.1, 1.3, CARD2);
  addAccentBar(s, 0.5, 1.7, 1.3);
  s.addText("惯性的定义", { x: 0.7, y: 1.85, w: 8.7, h: 0.3, fontSize: 11, color: BRAND, bold: true, margin: 0 });
  s.addText("物体保持原有运动状态不变的性质叫做惯性。", { x: 0.7, y: 2.25, w: 8.7, h: 0.45, fontSize: 15, color: WHITE, margin: 0 });
  s.addText("Inertia: The tendency of an object to resist changes in its motion.", { x: 0.7, y: 2.75, w: 8.7, h: 0.25, fontSize: 8, color: GRAY2, margin: 0 });

  // 要点
  const points = [
    { icon: "🔹", title: "固有属性", desc: "惯性是物体本身固有的属性，任何物体都有惯性" },
    { icon: "🔹", title: "与质量有关", desc: "质量越大，惯性越大；质量越小，惯性越小" },
    { icon: "🔹", title: "与速度无关", desc: "惯性大小只取决于质量，与速度大小无关" }
  ];

  points.forEach((pt, i) => {
    const cx = 0.5, cy = 3.2 + i * 0.75, cw = 9.0, ch = 0.65;
    addCard(s, cx, cy, cw, ch);
    s.addText(pt.icon, { x: cx + 0.2, y: cy + 0.15, w: 0.4, h: 0.35, fontSize: 14, margin: 0 });
    s.addText(pt.title, { x: cx + 0.7, y: cy + 0.15, w: 2.0, h: 0.35, fontSize: 11, bold: true, color: WHITE, margin: 0 });
    s.addText(pt.desc, { x: cx + 2.8, y: cy + 0.15, w: 6.0, h: 0.35, fontSize: 9, color: GRAY1, margin: 0 });
  });

  // 对比图示
  addCard(s, 5.5, 3.2, 4.1, 1.6, CARD);
  addAccentBar(s, 5.5, 3.2, 1.6);
  s.addText("质量对比", { x: 5.7, y: 3.35, w: 3.7, h: 0.25, fontSize: 10, color: BRAND, bold: true, margin: 0 });
  s.addText("🚗 小轿车", { x: 5.7, y: 3.7, w: 1.5, h: 0.3, fontSize: 10, color: GRAY1, margin: 0 });
  s.addText("质量小 → 惯性小", { x: 5.7, y: 4.05, w: 1.5, h: 0.25, fontSize: 8, color: GRAY2, margin: 0 });
  s.addText("🚛 大卡车", { x: 7.5, y: 3.7, w: 1.5, h: 0.3, fontSize: 10, color: GRAY1, margin: 0 });
  s.addText("质量大 → 惯性大", { x: 7.5, y: 4.05, w: 1.5, h: 0.25, fontSize: 8, color: ACCENT, bold: true, margin: 0 });
}

// ---------- SLIDE 9: 生活中的惯性 (1) ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Real-life Examples");
  addSlideTitle(s, "生活中的惯性现象（一）", "Inertia in Daily Life");

  // 急刹车例子
  addCard(s, 0.5, 1.7, 4.5, 3.0);
  addAccentBar(s, 0.5, 1.7, 3.0);
  s.addText("🚌 现象：急刹车时人向前倾", { x: 0.7, y: 1.85, w: 4.1, h: 0.35, fontSize: 13, bold: true, color: WHITE, margin: 0 });

  // 简单图示
  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 2.3, w: 3.0, h: 0.08, fill: { color: GRAY3 }, line: { color: GRAY3 } });
  s.addShape(pres.shapes.OVAL, { x: 2.0, y: 2.15, w: 0.3, h: 0.3, fill: { color: BRAND }, line: { color: BRAND } });
  s.addShape(pres.shapes.RECTANGLE, { x: 2.3, y: 2.3, w: 0.8, h: 0.05, fill: { color: ACCENT }, line: { color: ACCENT } });

  s.addText("解释", { x: 0.7, y: 2.6, w: 4.1, h: 0.25, fontSize: 10, color: BRAND, bold: true, margin: 0 });
  s.addText("1. 汽车和人都向前运动", { x: 0.7, y: 2.9, w: 4.1, h: 0.25, fontSize: 9, color: GRAY1, margin: 0 });
  s.addText("2. 刹车时，脚随车停止", { x: 0.7, y: 3.2, w: 4.1, h: 0.25, fontSize: 9, color: GRAY1, margin: 0 });
  s.addText("3. 上半身由于惯性保持向前运动", { x: 0.7, y: 3.5, w: 4.1, h: 0.25, fontSize: 9, color: GRAY1, margin: 0 });
  s.addText("4. 所以人向前倾", { x: 0.7, y: 3.8, w: 4.1, h: 0.25, fontSize: 9, color: GRAY1, margin: 0 });
  s.addText("👉 这就是为什么要系安全带！", { x: 0.7, y: 4.15, w: 4.1, h: 0.35, fontSize: 10, color: ACCENT, bold: true, margin: 0 });

  // 其他例子
  addCard(s, 5.3, 1.7, 4.3, 1.3, CARD2);
  addAccentBar(s, 5.3, 1.7, 1.3);
  s.addText("🏃 起跑时", { x: 5.5, y: 1.85, w: 3.9, h: 0.25, fontSize: 11, bold: true, color: WHITE, margin: 0 });
  s.addText("身体向后倾，因为身体要保持静止状态", { x: 5.5, y: 2.2, w: 3.9, h: 0.65, fontSize: 9, color: GRAY1, margin: 0 });

  addCard(s, 5.3, 3.2, 4.3, 1.3, CARD2);
  addAccentBar(s, 5.3, 3.2, 1.3);
  s.addText("🎢 过山车", { x: 5.5, y: 3.35, w: 3.9, h: 0.25, fontSize: 11, bold: true, color: WHITE, margin: 0 });
  s.addText("转弯时身体被甩向外侧，因为身体要保持原方向运动", { x: 5.5, y: 3.7, w: 3.9, h: 0.65, fontSize: 9, color: GRAY1, margin: 0 });
}

// ---------- SLIDE 10: 生活中的惯性 (2) ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "More Examples");
  addSlideTitle(s, "生活中的惯性现象（二）", "More Examples of Inertia");

  const examples = [
    {
      icon: "👕",
      title: "拍打衣服除灰尘",
      question: "为什么拍打衣服可以除去灰尘？",
      answer: "衣服受力运动，灰尘由于惯性保持静止，从而脱离衣服。"
    },
    {
      icon: "🏅",
      title: "跳远助跑",
      question: "跳远运动员为什么要助跑？",
      answer: "助跑获得速度后，由于惯性，起跳后身体会继续向前运动，跳得更远。"
    },
    {
      icon: "🔨",
      title: "锤头松动",
      question: "锤头松动时，为什么撞击锤柄下端可以紧固？",
      answer: "锤柄撞击后停止，锤头由于惯性继续向下运动，从而紧固。"
    }
  ];

  examples.forEach((ex, i) => {
    const cx = 0.5, cy = 1.7 + i * 1.05, cw = 9.0, ch = 0.95;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    s.addText(ex.icon, { x: cx + 0.2, y: cy + 0.15, w: 0.5, h: 0.5, fontSize: 20, margin: 0 });
    s.addText(ex.title, { x: cx + 0.8, y: cy + 0.15, w: 2.5, h: 0.35, fontSize: 12, bold: true, color: WHITE, margin: 0 });
    s.addText(ex.question, { x: cx + 3.5, y: cy + 0.15, w: 5.3, h: 0.35, fontSize: 9, color: GRAY1, margin: 0 });
    s.addText(ex.answer, { x: cx + 0.8, y: cy + 0.52, w: 8.0, h: 0.35, fontSize: 8, color: BRAND, margin: 0 });
  });

  // 互动区
  addCard(s, 0.5, 4.85, 9.1, 0.6, CARD2);
  s.addText("💬 互动：请同学尝试用惯性解释以上现象", { x: 0.7, y: 4.95, w: 8.7, h: 0.4, fontSize: 11, color: GRAY1, align: "center", margin: 0 });
}

// ---------- SLIDE 11: 课堂小结 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Summary");
  addSlideTitle(s, "课堂小结", "Key Takeaways");

  // 思维导图结构
  addCard(s, 0.5, 1.7, 9.1, 3.2, CARD2);
  addAccentBar(s, 0.5, 1.7, 3.2);

  // 中心主题
  s.addShape(pres.shapes.OVAL, { x: 4.2, y: 2.5, w: 1.6, h: 1.0, fill: { color: BRAND_DIM }, line: { color: BRAND, width: 1 } });
  s.addText("牛顿第一定律", { x: 4.3, y: 2.65, w: 1.4, h: 0.7, fontSize: 10, bold: true, color: WHITE, align: "center", margin: 0 });

  // 分支 1：定律内容
  s.addShape(pres.shapes.LINE, { x: 4.2, y: 3.0, w: 0.05, h: 1.2, fill: { color: GRAY3 }, line: { color: GRAY3 } });
  s.addShape(pres.shapes.LINE, { x: 4.2, y: 3.6, w: 1.8, h: 0.05, fill: { color: GRAY3 }, line: { color: GRAY3 } });
  s.addShape(pres.shapes.RECTANGLE, { x: 6.0, y: 3.3, w: 2.5, h: 0.9, fill: { color: CARD }, line: { color: BORDER } });
  s.addText("1. 定律内容", { x: 6.1, y: 3.4, w: 2.3, h: 0.3, fontSize: 9, bold: true, color: BRAND, margin: 0 });
  s.addText("一切物体不受力时", { x: 6.1, y: 3.7, w: 2.3, h: 0.25, fontSize: 7, color: GRAY1, margin: 0 });
  s.addText("保持静止或匀速直线运动", { x: 6.1, y: 3.95, w: 2.3, h: 0.25, fontSize: 7, color: GRAY1, margin: 0 });

  // 分支 2：惯性
  s.addShape(pres.shapes.LINE, { x: 4.2, y: 3.0, w: 0.05, h: 0.8, fill: { color: GRAY3 }, line: { color: GRAY3 } });
  s.addShape(pres.shapes.LINE, { x: 4.2, y: 2.6, w: -1.8, h: 0.05, fill: { color: GRAY3 }, line: { color: GRAY3 } });
  s.addShape(pres.shapes.RECTANGLE, { x: 1.5, y: 2.3, w: 2.5, h: 0.9, fill: { color: CARD }, line: { color: BORDER } });
  s.addText("2. 惯性", { x: 1.6, y: 2.4, w: 2.3, h: 0.3, fontSize: 9, bold: true, color: BRAND, margin: 0 });
  s.addText("定义：保持运动状态不变的性质", { x: 1.6, y: 2.7, w: 2.3, h: 0.25, fontSize: 7, color: GRAY1, margin: 0 });
  s.addText("只与质量有关", { x: 1.6, y: 2.95, w: 2.3, h: 0.25, fontSize: 7, color: GRAY1, margin: 0 });

  // 分支 3：力与运动
  s.addShape(pres.shapes.LINE, { x: 4.2, y: 3.0, w: 0.05, h: 0.3, fill: { color: GRAY3 }, line: { color: GRAY3 } });
  s.addShape(pres.shapes.LINE, { x: 4.2, y: 3.15, w: 1.5, h: 0.05, fill: { color: GRAY3 }, line: { color: GRAY3 }, rotate: 45 });
  s.addShape(pres.shapes.RECTANGLE, { x: 5.7, y: 2.3, w: 2.5, h: 0.9, fill: { color: CARD }, line: { color: BORDER } });
  s.addText("3. 力与运动", { x: 5.8, y: 2.4, w: 2.3, h: 0.3, fontSize: 9, bold: true, color: BRAND, margin: 0 });
  s.addText("力不是维持运动的原因", { x: 5.8, y: 2.7, w: 2.3, h: 0.25, fontSize: 7, color: GRAY1, margin: 0 });
  s.addText("力是改变运动状态的原因", { x: 5.8, y: 2.95, w: 2.3, h: 0.25, fontSize: 7, color: GRAY1, margin: 0 });

  // 分支 4：科学方法
  s.addShape(pres.shapes.LINE, { x: 4.2, y: 3.0, w: 0.05, h: 0.3, fill: { color: GRAY3 }, line: { color: GRAY3 } });
  s.addShape(pres.shapes.LINE, { x: 4.2, y: 3.15, w: -1.5, h: 0.05, fill: { color: GRAY3 }, line: { color: GRAY3 }, rotate: -45 });
  s.addShape(pres.shapes.RECTANGLE, { x: 1.5, y: 3.3, w: 2.5, h: 0.9, fill: { color: CARD }, line: { color: BORDER } });
  s.addText("4. 科学方法", { x: 1.6, y: 3.4, w: 2.3, h: 0.3, fontSize: 9, bold: true, color: BRAND, margin: 0 });
  s.addText("理想实验方法", { x: 1.6, y: 3.7, w: 2.3, h: 0.25, fontSize: 7, color: GRAY1, margin: 0 });
  s.addText("实验 + 推理", { x: 1.6, y: 3.95, w: 2.3, h: 0.25, fontSize: 7, color: GRAY1, margin: 0 });
}

// ---------- SLIDE 12: 课后作业 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Homework");
  addSlideTitle(s, "课后作业", "Homework Assignment");

  const assignments = [
    {
      icon: "📚",
      title: "基础练习",
      desc: "完成练习册相关习题，重点复习牛顿第一定律内容和惯性概念。",
      color: BRAND
    },
    {
      icon: "🔍",
      title: "思考题",
      desc: "思考：汽车安全带为什么要系紧？用惯性知识解释。",
      color: ACCENT
    },
    {
      icon: "✍️",
      title: "拓展作业",
      desc: "撰写一篇关于'交通安全与惯性'的短文（200 字左右）。",
      color: WHITE
    },
    {
      icon: "📖",
      title: "预习",
      desc: "预习下一节：二力平衡",
      color: GRAY1
    }
  ];

  assignments.forEach((hw, i) => {
    const cx = 0.5 + (i % 2) * 4.8, cy = 1.7 + Math.floor(i / 2) * 1.5, cw = 4.55, ch = 1.35;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    s.addText(hw.icon, { x: cx + 0.2, y: cy + 0.2, w: 0.5, h: 0.5, fontSize: 20, margin: 0 });
    s.addText(hw.title, { x: cx + 0.8, y: cy + 0.2, w: 3.5, h: 0.35, fontSize: 12, bold: true, color: hw.color, margin: 0 });
    s.addText(hw.desc, { x: cx + 0.2, y: cy + 0.65, w: 4.15, h: 0.55, fontSize: 9, color: GRAY1, margin: 0 });
  });

  // 底部提示
  addCard(s, 0.5, 4.75, 9.1, 0.6, CARD2);
  s.addText("⏰ 下次课检查作业，请认真完成！", { x: 0.7, y: 4.85, w: 8.7, h: 0.4, fontSize: 11, color: ACCENT, align: "center", bold: true, margin: 0 });
}

// ---------- SLIDE 13: 结束页 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addText("THANK YOU", { x: 0.5, y: 1.2, w: 9, h: 0.3, fontSize: 10, color: BRAND, bold: true, charSpacing: 8, align: "center", margin: 0 });

  s.addText([
    { text: "谢谢聆听！", options: { color: WHITE, bold: true } }
  ], { x: 0.5, y: 1.8, w: 9, h: 0.8, fontSize: 42, align: "center", margin: 0 });

  s.addText("物理探索无止境", { x: 0.5, y: 2.7, w: 9, h: 0.4, fontSize: 16, color: GRAY1, align: "center", margin: 0 });
  s.addText("Keep Exploring the Wonders of Physics", { x: 0.5, y: 3.15, w: 9, h: 0.25, fontSize: 9, color: GRAY2, align: "center", margin: 0 });

  // 分隔线
  s.addShape(pres.shapes.RECTANGLE, { x: 3.5, y: 3.6, w: 3.0, h: 0.04, fill: { color: BRAND }, line: { color: BRAND } });

  // 底部装饰
  s.addText("🔬 ⚛️ 🌌", { x: 0.5, y: 4.0, w: 9, h: 0.4, fontSize: 24, align: "center", margin: 0 });

  // 名言
  addCard(s, 2.5, 4.5, 5.0, 0.8, CARD2);
  s.addText("'如果说我看得比别人更远，那是因为我站在巨人的肩膀上。'", { x: 2.7, y: 4.6, w: 4.6, h: 0.6, fontSize: 9, color: GRAY1, align: "center", margin: 0 });
  s.addText("— 艾萨克·牛顿", { x: 2.7, y: 5.05, w: 4.6, h: 0.2, fontSize: 7, color: BRAND, align: "center", margin: 0 });
}

// =============================================
// 💾 输出文件
// =============================================
const outputDir = process.env.AGENT_OUTPUT_DIR || ".";
const outputPath = path.join(outputDir, "牛顿第一定律课件.pptx");

pres.writeFile({ fileName: outputPath })
  .then(() => console.log("✅ 生成成功：", outputPath))
  .catch(e => { console.error("❌ 错误:", e); process.exit(1); });
