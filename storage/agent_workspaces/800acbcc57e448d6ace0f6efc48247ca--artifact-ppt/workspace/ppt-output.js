const pptxgen = require("pptxgenjs"); 
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "牛顿第一定律";

// =============================================
// 🎨 设计系统 — 明亮清新的教学配色
// =============================================
const BG     = "F1F8FF";  // 浅蓝色背景
const CARD   = "B3E5FC";  // 浅蓝色卡片
const CARD2  = "FFEB3B";  // 柠檬黄卡片
const WHITE  = "FFFFFF";  // 白色
const GRAY1  = "D1D1D1";  // 浅灰色
const GRAY2  = "A4A4A4";  // 灰色
const GRAY3  = "707070";  // 深灰色
const BORDER = "B0BEC5";  // 边框色

const BRAND     = "00AEEF";   // 亮蓝色
const BRAND_DIM = "006F8E";   // 品牌色暗化版

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
  slide.addText(zh, { x:0.5, y,       w:9, h:0.55, fontSize:28, bold:true, color:WHITE, margin:0 });
  slide.addText(en, { x:0.5, y:y+0.52, w:9, h:0.22, fontSize:10,           color:GRAY2, margin:0 });
}

function addIconCircle(slide, icon, x, y, size=0.45) {
  slide.addShape(pres.shapes.OVAL, {
    x, y, w:size, h:size,
    fill: { color: BRAND_DIM }, line: { color: BRAND, width: 0.5 }
  });
  slide.addText(icon, { x, y, w:size, h:size, fontSize:size*22, align:"center", valign:"middle", margin:0 });
}

// =============================================
// 📑 幻灯片内容
// =============================================

// ---------- SLIDE 1: 封面 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addText("初三物理 · 第八章", { x:0.5, y:0.38, w:6, h:0.2, fontSize:9, color:GRAY2, charSpacing:4, margin:0 });

  s.addText([
    { text: "牛", options: { color: BRAND, bold: true } },
    { text: "顿第一定律", options: { color: WHITE, bold: true } }
  ], { x:0.5, y:0.85, w:6, h:1.0, fontSize:52, margin:0 });

  s.addText("Newton's First Law of Motion", { x:0.5, y:2.6, w:6, h:0.3, fontSize:13, color:GRAY1, margin:0 });

  s.addShape(pres.shapes.RECTANGLE, { x:0.5, y:3.1, w:1.2, h:0.04, fill:{ color:BRAND }, line:{ color:BRAND } });

  const metas = [["40 分钟","课时"], ["初三","年级"], ["物理","学科"], ["新授","课型"]];
  metas.forEach(([v, k], i) => {
    const bx = 0.5 + i * 1.5;
    addCard(s, bx, 3.3, 1.3, 0.72);
    s.addText(v, { x:bx, y:3.33, w:1.3, h:0.3,  fontSize:18, bold:true, color:BRAND, align:"center", margin:0 });
    s.addText(k, { x:bx, y:3.65, w:1.3, h:0.18, fontSize:7,            color:GRAY2, align:"center", margin:0 });
  });

  s.addText("🎯 理解定律 · 掌握惯性 · 解释现象", { x:0.5, y:4.8, w:9, h:0.4, fontSize:14, color:BRAND, align:"center", bold:true, margin:0 });
}

// ---------- SLIDE 2: 学习目标 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Learning Objectives");
  addSlideTitle(s, "本节课学习目标", "What We Will Learn Today");

  const items = [
    { icon:"📖", title:"理解牛顿第一定律", sub:"掌握定律内容", body:"知道定律是力学基本定律之一，理解'不受外力'的理想模型意义。" },
    { icon:"💡", title:"理解惯性概念", sub:"物体固有属性", body:"惯性是物体保持原来运动状态不变的性质，只与质量有关。" },
    { icon:"🔍", title:"解释生活现象", sub:"学以致用", body:"能够用惯性知识解释刹车、跳远等实际生活中的现象。" },
  ];
  items.forEach((item, i) => {
    const cx = 0.28, cy = 1.6 + i * 1.3, cw = 9.44, ch = 1.15;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    addIconCircle(s, item.icon, cx+0.18, cy+0.2);
    s.addText(item.title, { x:cx+0.72, y:cy+0.18, w:cw-0.8, h:0.28, fontSize:15, bold:true, color:WHITE, margin:0 });
    s.addText(item.sub,   { x:cx+0.72, y:cy+0.46, w:cw-0.8, h:0.18, fontSize:8,           color:GRAY2, margin:0 });
    s.addText(item.body,  { x:cx+0.18, y:cy+0.78, w:cw-0.25,h:0.32, fontSize:9.5,         color:GRAY1, margin:0 });
  });
}

// ---------- SLIDE 3: 重点内容（简化版）----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Key Points");
  addSlideTitle(s, "三大重点内容", "Three Key Points · Simplified");

  const cards = [
    { title:"定律内容", sub:"CORE CONTENT", num:"①", numSub:"核心", lines:["一切物体", "不受力时", "保持静止或匀速直线运动"], tag:"重点掌握", accent:true },
    { title:"惯性概念", sub:"INERTIA", num:"②", numSub:"属性", lines:["保持原状态", "只与质量有关", "与速度无关"], tag:"易错点", accent:false },
    { title:"解释现象", sub:"APPLICATION", num:"③", numSub:"应用", lines:["刹车前倾", "拍打灰尘", "跳远助跑"], tag:"必考", accent:false },
  ];
  cards.forEach((c, i) => {
    const cx = 0.28 + i * 3.22, cy = 1.55, cw = 3.05, ch = 3.8;
    s.addShape(pres.shapes.RECTANGLE, {
      x:cx, y:cy, w:cw, h:ch,
      fill: { color: c.accent ? BRAND_DIM : CARD },
      line: { color: c.accent ? BRAND : BORDER, width: c.accent ? 1 : 0.5 },
      shadow: makeShadow()
    });
    addAccentBar(s, cx, cy, ch);
    s.addText(c.sub,   { x:cx+0.15, y:cy+0.18, w:cw-0.2, h:0.18, fontSize:7,  color:GRAY2, charSpacing:2, margin:0 });
    s.addText(c.title, { x:cx+0.15, y:cy+0.38, w:cw-0.2, h:0.32, fontSize:15, bold:true, color:WHITE, margin:0 });
    s.addText(c.num,   { x:cx+0.15, y:cy+0.82, w:cw-0.2, h:0.65, fontSize:36, bold:true, color:BRAND, margin:0 });
    s.addText(c.numSub,{ x:cx+0.15, y:cy+1.48, w:cw-0.2, h:0.18, fontSize:7.5,color:GRAY2, margin:0 });
    s.addShape(pres.shapes.RECTANGLE, { x:cx+0.15, y:cy+1.72, w:0.4, h:0.03, fill:{color:BRAND}, line:{color:BRAND} });
    c.lines.forEach((l, li) => {
      s.addText(l, { x:cx+0.15, y:cy+1.88+li*0.32, w:cw-0.2, h:0.26, fontSize:10, color:GRAY1, margin:0 });
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x:cx+0.15, y:cy+3.35, w:0.9, h:0.24, fill:{color:BRAND_DIM}, line:{color:BRAND,width:0.5}, rectRadius:0.05 });
    s.addText(c.tag, { x:cx+0.15, y:cy+3.35, w:0.9, h:0.24, fontSize:8, color:BRAND, bold:true, align:"center", margin:0 });
  });
}

// ---------- SLIDE 4: 牛顿第一定律内容 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Law Content");
  addSlideTitle(s, "牛顿第一定律", "Newton's First Law");

  const lx = 0.28, ly = 1.55, lw = 5.5, lh = 3.85;
  s.addShape(pres.shapes.RECTANGLE, { x:lx, y:ly, w:lw, h:lh, fill:{color:BRAND_DIM}, line:{color:BRAND,width:1}, shadow:makeShadow() });
  addAccentBar(s, lx, ly, lh);
  
  s.addText("定律内容", { x:lx+0.2, y:ly+0.18, w:lw-0.3, h:0.2,  fontSize:9,  color:BRAND, charSpacing:2, margin:0 });
  
  s.addText("一切物体", { x:lx+0.2, y:ly+0.6,  w:lw-0.3, h:0.5,  fontSize:24, bold:true, color:WHITE, margin:0 });
  s.addText("在没有受到力的作用时", { x:lx+0.2, y:ly+1.15,  w:lw-0.3, h:0.4,  fontSize:18, color:GRAY1, margin:0 });
  s.addText("总保持", { x:lx+0.2, y:ly+1.6,  w:lw-0.3, h:0.4,  fontSize:18, color:GRAY1, margin:0 });
  s.addText("静止状态 或 匀速直线运动状态", { x:lx+0.2, y:ly+2.05,  w:lw-0.3, h:0.6,  fontSize:20, bold:true, color:BRAND, margin:0 });
  
  s.addShape(pres.shapes.RECTANGLE, { x:lx+0.2, y:ly+2.8, w:lw-0.4, h:0.02, fill:{color:GRAY3}, line:{color:GRAY3} });

  s.addText("⚠ 关键词解读", { x:lx+0.2, y:ly+3.0, w:lw-0.3, h:0.2, fontSize:10, bold:true, color:BRAND, margin:0 });
  s.addText("• 一切：所有物体，没有例外", { x:lx+0.2, y:ly+3.25, w:lw-0.3, h:0.2, fontSize:9,  color:GRAY1,  margin:0 });
  s.addText("• 不受力：理想模型，实际不存在", { x:lx+0.2, y:ly+3.5, w:lw-0.3, h:0.2, fontSize:9,  color:GRAY1,  margin:0 });
  s.addText("• 或：两种状态必居其一", { x:lx+0.2, y:ly+3.75, w:lw-0.3, h:0.2, fontSize:9,  color:GRAY1,  margin:0 });

  const rx = 6.0, ry = 1.55, rw = 3.72;
  addCard(s, rx, ry, rw, 1.8);
  addAccentBar(s, rx, ry, 1.8);
  s.addText("🧪 实验方法", { x:rx+0.2, y:ry+0.15, w:rw-0.3, h:0.2, fontSize:9, color:BRAND, bold:true, margin:0 });
  s.addText("实验 + 科学推理", { x:rx+0.2, y:ry+0.45, w:rw-0.3, h:0.35, fontSize:14, bold:true, color:WHITE, margin:0 });
  s.addText("伽利略理想斜面实验", { x:rx+0.2, y:ry+0.9, w:rw-0.3, h:0.25, fontSize:9, color:GRAY1, margin:0 });

  addCard(s, rx, ry+2.0, rw, 1.8);
  addAccentBar(s, rx, ry+2.0, 1.8);
  s.addText("💡 力与运动", { x:rx+0.2, y:ry+2.15, w:rw-0.3, h:0.2, fontSize:9, color:BRAND, bold:true, margin:0 });
  s.addText("力不是维持运动的原因", { x:rx+0.2, y:ry+2.45, w:rw-0.3, h:0.35, fontSize:10, bold:true, color:WHITE, margin:0 });
  s.addText("力是改变运动状态的原因", { x:rx+0.2, y:ry+2.9, w:rw-0.3, h:0.35, fontSize:10, bold:true, color:WHITE, margin:0 });
}

// ---------- SLIDE 5: 惯性概念 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Inertia Concept");
  addSlideTitle(s, "惯性 · 物体固有属性", "Inertia · Natural Property");

  const items = [
    { icon:"①", title:"定义", sub:"DEFINITION", body:"物体保持原来运动状态不变的性质叫惯性。", highlight:true },
    { icon:"②", title:"特点", sub:"CHARACTERISTICS", body:"• 一切物体都有惯性\n• 惯性是属性，不是力\n• 不能说受到惯性", highlight:false },
    { icon:"③", title:"决定因素", sub:"DEPENDS ON", body:"惯性大小只与质量有关\n质量越大，惯性越大\n与速度、运动状态无关", highlight:false },
  ];
  items.forEach((item, i) => {
    const cx = 0.28 + i * 3.22, cy = 1.55, cw = 3.05, ch = 3.8;
    s.addShape(pres.shapes.RECTANGLE, {
      x:cx, y:cy, w:cw, h:ch,
      fill: { color: item.highlight ? BRAND_DIM : CARD },
      line: { color: item.highlight ? BRAND : BORDER, width: item.highlight ? 1 : 0.5 },
      shadow: makeShadow()
    });
    addAccentBar(s, cx, cy, ch);
    addIconCircle(s, item.icon, cx+0.22, cy+0.25);
    s.addText(item.sub,   { x:cx+0.82, y:cy+0.28, w:cw-0.9, h:0.18, fontSize:7,  color:GRAY2, margin:0 });
    s.addText(item.title, { x:cx+0.82, y:cy+0.48, w:cw-0.9, h:0.32, fontSize:15, bold:true, color:WHITE, margin:0 });
    s.addText(item.body,  { x:cx+0.18, y:cy+0.95, w:cw-0.25,h:2.5,  fontSize:9.5, color:GRAY1, margin:0 });
  });

  s.addShape(pres.shapes.RECTANGLE, { x:0.28, y:4.8, w:9.44, h:0.6, fill:{color:CARD2}, line:{color:"FBC02D",width:0.5}, shadow:makeShadow() });
  s.addText("⚠ 常见误区：速度大的物体惯性大？错！惯性只与质量有关！", { x:0.28, y:4.85, w:9.44, h:0.5, fontSize:11, bold:true, color:"F57F17", align:"center", margin:0 });
}

// ---------- SLIDE 6: 惯性现象解释 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Application");
  addSlideTitle(s, "用惯性解释现象", "Explaining Phenomena with Inertia");

  addCard(s, 0.28, 1.55, 4.5, 3.85);
  addAccentBar(s, 0.28, 1.55, 3.85);
  s.addText("📝 解释步骤", { x:0.48, y:1.7, w:4.2, h:0.25, fontSize:11, bold:true, color:BRAND, margin:0 });
  
  const steps = [
    ["1️⃣", "确定研究对象", "明确要分析的是哪个物体"],
    ["2️⃣", "分析原来状态", "物体原来是静止还是运动"],
    ["3️⃣", "受力改变情况", "哪个部分受力，运动状态如何改变"],
    ["4️⃣", "惯性保持", "另一部分由于惯性保持原状态"],
    ["5️⃣", "现象结果", "产生什么现象"]
  ];
  steps.forEach((step, i) => {
    s.addText(step[0], { x:0.48, y:2.1+i*0.55, w:0.4, h:0.35, fontSize:14, margin:0 });
    s.addText(step[1], { x:0.95, y:2.1+i*0.55, w:2.5, h:0.25, fontSize:10, bold:true, color:WHITE, margin:0 });
    s.addText(step[2], { x:0.95, y:2.32+i*0.55, w:3.5, h:0.2, fontSize:8.5, color:GRAY1, margin:0 });
  });

  const examples = [
    { icon:"🚗", title:"汽车刹车", desc:"人向前倾", detail:"人随车前进 → 刹车脚停 → 上身惯性继续向前" },
    { icon:"👕", title:"拍打衣服", desc:"灰尘掉落", detail:"衣服受力运动 → 灰尘惯性保持静止 → 分离掉落" },
    { icon:"🏃", title:"跳远助跑", desc:"跳得更远", detail:"助跑获得速度 → 起跳后惯性保持水平运动" },
  ];
  examples.forEach((ex, i) => {
    const cx = 5.0, cy = 1.55 + i * 1.25, cw = 4.72, ch = 1.1;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    addIconCircle(s, ex.icon, cx+0.18, cy+0.2, 0.4);
    s.addText(ex.title, { x:cx+0.68, y:cy+0.18, w:cw-0.8, h:0.25, fontSize:12, bold:true, color:WHITE, margin:0 });
    s.addText(ex.desc, { x:cx+0.68, y:cy+0.45, w:cw-0.8, h:0.2, fontSize:8.5, color:BRAND, bold:true, margin:0 });
    s.addText(ex.detail, { x:cx+0.18, y:cy+0.72, w:cw-0.25, h:0.3, fontSize:8.5, color:GRAY1, margin:0 });
  });
}

// ---------- SLIDE 7: 难点突破 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Difficult Points");
  addSlideTitle(s, "难点突破", "Overcoming Difficulties");

  const cards = [
    { icon:"❌", title:"纠正错误观念", sub:"CORRECT MISCONCEPTION", body:"错误：力是维持运动的原因\n正确：力是改变运动状态的原因\n\n亚里士多德观点 vs 牛顿观点", tag:"重点纠正" },
    { icon:"💭", title:"理解理想模型", sub:"IDEAL MODEL", body:"不受外力在现实中不存在\n是理想化模型\n\n帮助我们理解本质规律", tag:"抽象思维" },
    { icon:"⚖️", title:"辨析惯性大小", sub:"INERTIA SIZE", body:"惯性大小只看质量\n与速度无关\n与运动状态无关\n\n质量是唯一决定因素", tag:"易错考点" },
  ];
  cards.forEach((c, i) => {
    const cx = 0.28 + i * 3.22, cy = 1.55, cw = 3.05, ch = 3.8;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    addIconCircle(s, c.icon, cx+0.22, cy+0.25);
    s.addText(c.sub, { x:cx+0.82, y:cy+0.28, w:cw-0.9, h:0.18, fontSize:6.5,  color:GRAY2, margin:0 });
    s.addText(c.title, { x:cx+0.82, y:cy+0.48, w:cw-0.9, h:0.35, fontSize:13, bold:true, color:WHITE, margin:0 });
    s.addText(c.body, { x:cx+0.18, y:cy+0.95, w:cw-0.25, h:2.3, fontSize:8.5, color:GRAY1, margin:0 });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x:cx+0.18, y:cy+3.35, w:0.9, h:0.24, fill:{color:BRAND_DIM}, line:{color:BRAND,width:0.5}, rectRadius:0.05 });
    s.addText(c.tag, { x:cx+0.18, y:cy+3.35, w:0.9, h:0.24, fontSize:7.5, color:BRAND, bold:true, align:"center", margin:0 });
  });
}

// ---------- SLIDE 8: 课堂小结 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addText("SUMMARY", { x:0.5, y:0.5, w:9, h:0.22, fontSize:8, color:BRAND, bold:true, charSpacing:4, align:"center", margin:0 });
  s.addText([
    { text:"牛顿第一定律",   options:{ color:BRAND } },
    { text:"与", options:{ color:WHITE } },
    { text:"惯性", options:{ color:BRAND } },
    { text:"概念", options:{ color:WHITE } },
  ], { x:0.5, y:0.9, w:9, h:0.8, fontSize:40, bold:true, align:"center", margin:0 });
  s.addText("课堂小结 · 核心回顾", { x:0.5, y:1.68, w:9, h:0.65, fontSize:32, bold:true, color:WHITE, align:"center", margin:0 });
  s.addText("Newton's First Law and Inertia", { x:0.5, y:2.42, w:9, h:0.25, fontSize:10, color:GRAY2, align:"center", margin:0 });

  const summaryPoints = [
    ["📖", "定律内容", "不受力 → 静止或匀速直线运动"],
    ["💡", "惯性概念", "保持原状态的性质，只与质量有关"],
    ["🔍", "解释方法", "原状态 → 受力变 → 惯性保持 → 现象"],
  ];
  summaryPoints.forEach((c, i) => {
    const cx = 1.5 + i * 2.5, cy = 3.0, cw = 2.3, ch = 2.0;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    addIconCircle(s, c[0], cx+0.87, cy+0.2, 0.52);
    s.addText(c[1], { x:cx+0.1, y:cy+0.88, w:cw-0.2, h:0.32, fontSize:13, bold:true, color:WHITE, align:"center", margin:0 });
    s.addText(c[2], { x:cx+0.1, y:cy+1.28, w:cw-0.2, h:0.6,  fontSize:9, color:GRAY1, align:"center", margin:0 });
  });

  s.addText("✅ 90% 学生能复述定律 · 80% 学生能解释现象", { x:0.5, y:5.2, w:9, h:0.3, fontSize:10, color:BRAND, align:"center", margin:0 });
}

// =============================================
// 💾 输出文件
// =============================================
const outputDir = process.env.AGENT_OUTPUT_DIR || ".";
const outputPath = outputDir + "/newton-first-law.pptx";

pres.writeFile({ fileName: outputPath })
  .then(() => console.log("✅ 生成成功:", outputPath))
  .catch(e => { console.error("❌ 错误:", e); process.exit(1); });
