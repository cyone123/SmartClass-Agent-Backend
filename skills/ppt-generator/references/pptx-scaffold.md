# .pptx 直出脚手架

使用 pptxgenjs 生成 `.pptx` 文件的完整模板。复制 `scaffold.js` 后按主题填充内容即可。

---

## scaffold.js — 完整可运行模板

将以下代码保存为 `workspace/ppt-output.js`，按注释替换内容：

```javascript
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "演示标题";  // ← 修改

// =============================================
// 🎨 设计系统 — 无需改动，复用即可
// =============================================
const BG     = "000000";
const CARD   = "1A1A1A";
const CARD2  = "222222";
const WHITE  = "FFFFFF";
const GRAY1  = "AAAAAA";
const GRAY2  = "666666";
const GRAY3  = "333333";
const BORDER = "2A2A2A";

// ← 根据内容识别品牌色，例如：
// 小米: "FF6900" | 华为: "CF0A2C" | 特斯拉: "CC0000"
// 苹果: "0071E3" | 字节: "006EFF" | 阿里: "FF6A00"
// 通用科技蓝: "00AEEF"
const BRAND     = "FF6900";   // ← 改这里
const BRAND_DIM = "1A0900";   // ← 改这里（品牌色暗化版，约10%亮度）

// makeShadow 必须是函数，每次调用返回新对象（pptxgenjs 会修改传入的对象）
const makeShadow = () => ({ type:"outer", blur:8, offset:2, angle:135, color:"000000", opacity:0.25 });

// 卡片背景 + 边框 + 阴影
function addCard(slide, x, y, w, h, color=CARD) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color },
    line: { color: BORDER, width: 0.5 },
    shadow: makeShadow()
  });
}

// 品牌色左侧细竖条（视觉锚点）
function addAccentBar(slide, x, y, h) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 0.06, h,
    fill: { color: BRAND }, line: { color: BRAND }
  });
}

// 版块小标签（全大写，间距）
function addSectionLabel(slide, text, y=0.28) {
  slide.addText(text.toUpperCase(), {
    x:0.5, y, w:9, h:0.22,
    fontSize:8, color:BRAND, bold:true, charSpacing:4, margin:0
  });
}

// 幻灯片主标题 + 英文副标题
function addSlideTitle(slide, zh, en, y=0.55) {
  slide.addText(zh, { x:0.5, y,       w:9, h:0.55, fontSize:28, bold:true, color:WHITE, margin:0 });
  slide.addText(en, { x:0.5, y:y+0.52, w:9, h:0.22, fontSize:10,           color:GRAY2, margin:0 });
}

// 图标圆圈（用文字/emoji 替代图标）
function addIconCircle(slide, icon, x, y, size=0.45) {
  slide.addShape(pres.shapes.OVAL, {
    x, y, w:size, h:size,
    fill: { color: BRAND_DIM }, line: { color: BRAND, width: 0.5 }
  });
  slide.addText(icon, { x, y, w:size, h:size, fontSize:size*22, align:"center", valign:"middle", margin:0 });
}

// =============================================
// 📑 幻灯片内容 — 在这里填充每张幻灯片
// =============================================

// ---------- SLIDE 1: 封面 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };

  // 顶部小标签
  s.addText("COMPANY · TOPIC · DATE", { x:0.5, y:0.38, w:6, h:0.2, fontSize:7, color:GRAY2, charSpacing:4, margin:0 });

  // 主标题（支持品牌色混排）
  s.addText([
    { text: "主", options: { color: BRAND, bold: true } },
    { text: "标题", options: { color: WHITE, bold: true } }
  ], { x:0.5, y:0.85, w:6, h:1.0, fontSize:52, margin:0 });

  s.addText("副标题 / Subtitle", { x:0.5, y:2.6, w:6, h:0.3, fontSize:13, color:GRAY1, margin:0 });

  // 分隔线
  s.addShape(pres.shapes.RECTANGLE, { x:0.5, y:3.1, w:1.2, h:0.04, fill:{ color:BRAND }, line:{ color:BRAND } });

  // 底部 4 个 meta 数据小卡
  const metas = [["值1","标签1"], ["值2","标签2"], ["值3","标签3"], ["值4","标签4"]];
  metas.forEach(([v, k], i) => {
    const bx = 0.5 + i * 1.5;
    addCard(s, bx, 3.3, 1.3, 0.72);
    s.addText(v, { x:bx, y:3.33, w:1.3, h:0.3,  fontSize:18, bold:true, color:BRAND, align:"center", margin:0 });
    s.addText(k, { x:bx, y:3.65, w:1.3, h:0.18, fontSize:7,            color:GRAY2, align:"center", margin:0 });
  });

  // 右侧 3 个排名/指标卡
  [["指标1","说明"], ["指标2","说明"], ["指标3","说明"]].forEach(([v, k], i) => {
    addCard(s, 7.0, 0.6 + i * 1.55, 2.6, 1.3);
    addAccentBar(s, 7.0, 0.6 + i * 1.55, 1.3);
    s.addText(v, { x:7.1, y:0.6+i*1.55+0.22, w:2.4, h:0.45, fontSize:22, bold:true, color:BRAND, align:"center", margin:0 });
    s.addText(k, { x:7.1, y:0.6+i*1.55+0.7,  w:2.4, h:0.22, fontSize:8,            color:GRAY2, align:"center", margin:0 });
  });
}

// ---------- SLIDE 2: 三列矩阵页 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Section Label");
  addSlideTitle(s, "页面中文标题", "English Subtitle · Description");

  // 3 个等宽卡片
  const cards = [
    { title:"卡片1", sub:"SUBTITLE A", num:"309B", numSub:"说明文字", lines:["要点1","要点2","要点3"], tag:"标签", accent:true },
    { title:"卡片2", sub:"SUBTITLE B", num:"1T+",  numSub:"说明文字", lines:["要点1","要点2","要点3"], tag:"标签", accent:false },
    { title:"卡片3", sub:"SUBTITLE C", num:"双模", numSub:"说明文字", lines:["要点1","要点2","要点3"], tag:"标签", accent:false },
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
      s.addText(l, { x:cx+0.15, y:cy+1.88+li*0.32, w:cw-0.2, h:0.26, fontSize:9, color:GRAY1, margin:0 });
    });
    // tag pill
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x:cx+0.15, y:cy+3.35, w:0.9, h:0.24, fill:{color:BRAND_DIM}, line:{color:BRAND,width:0.5}, rectRadius:0.05 });
    s.addText(c.tag, { x:cx+0.15, y:cy+3.35, w:0.9, h:0.24, fontSize:7.5, color:BRAND, bold:true, align:"center", margin:0 });
  });
}

// ---------- SLIDE 3: 2×2 内容卡页 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Section Label");
  addSlideTitle(s, "四格内容页标题", "Four Card Layout · Details");

  const items = [
    { icon:"①", title:"标题一", sub:"English Sub", body:"详细内容文字。要点描述，支持长文本自动换行。" },
    { icon:"②", title:"标题二", sub:"English Sub", body:"详细内容文字。要点描述，支持长文本自动换行。" },
    { icon:"③", title:"标题三", sub:"English Sub", body:"详细内容文字。要点描述，支持长文本自动换行。" },
    { icon:"④", title:"标题四", sub:"English Sub", body:"详细内容文字。要点描述，支持长文本自动换行。" },
  ];
  items.forEach((item, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const cx = 0.28 + col * 4.8, cy = 1.6 + row * 1.85, cw = 4.55, ch = 1.65;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    addIconCircle(s, item.icon, cx+0.18, cy+0.2);
    s.addText(item.title, { x:cx+0.72, y:cy+0.18, w:cw-0.8, h:0.28, fontSize:13, bold:true, color:WHITE, margin:0 });
    s.addText(item.sub,   { x:cx+0.72, y:cy+0.46, w:cw-0.8, h:0.18, fontSize:7.5,           color:GRAY2, margin:0 });
    s.addText(item.body,  { x:cx+0.18, y:cy+0.78, w:cw-0.25,h:0.72, fontSize:8.5,           color:GRAY1, margin:0 });
  });
}

// ---------- SLIDE 4: 数据对比页（左表+右数字卡）----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Benchmark / Data");
  addSlideTitle(s, "数据对比页标题", "Comparison · Data Analysis");

  // 左侧对比表格卡
  const tx = 0.28, ty = 1.55, tw = 5.8, th = 3.85;
  addCard(s, tx, ty, tw, th);
  s.addText("表格说明标题", { x:tx+0.2, y:ty+0.15, w:5, h:0.2, fontSize:8, color:GRAY2, charSpacing:2, margin:0 });

  const headers = ["对比维度","指标A","指标B","指标C"];
  const colXs   = [tx+0.2, tx+2.0, tx+3.3, tx+4.6];
  headers.forEach((h, i) => s.addText(h, { x:colXs[i], y:ty+0.45, w:1.2, h:0.22, fontSize:8, color:GRAY2, bold:true, margin:0 }));
  s.addShape(pres.shapes.RECTANGLE, { x:tx+0.1, y:ty+0.7, w:tw-0.2, h:0.02, fill:{color:GRAY3}, line:{color:GRAY3} });

  const rows = [
    { name:"本产品",   vals:["98%","96.2","91.7%"], highlight:true },
    { name:"竞品 A",   vals:["93.1%","—","—"],       highlight:false },
    { name:"竞品 B",   vals:["91.3%","—","—"],       highlight:false },
  ];
  rows.forEach((row, ri) => {
    const ry = ty + 0.82 + ri * 0.72;
    s.addText(row.name, { x:colXs[0], y:ry, w:1.7, h:0.28, fontSize:row.highlight?10:9, bold:row.highlight, color:row.highlight?BRAND:GRAY1, margin:0 });
    row.vals.forEach((v, vi) => s.addText(v, { x:colXs[vi+1], y:ry, w:1.2, h:0.28, fontSize:10, bold:row.highlight, color:row.highlight?BRAND:GRAY2, margin:0 }));
    if (ri < rows.length-1) s.addShape(pres.shapes.RECTANGLE, { x:tx+0.1, y:ry+0.36, w:tw-0.2, h:0.01, fill:{color:GRAY3}, line:{color:GRAY3} });
  });

  // 右侧 3 个大数字卡
  [["98%","核心指标A","Key Metric A"],["96.2","核心指标B","Key Metric B"],["91.7%","核心指标C","Key Metric C"]].forEach(([num, label, sub], i) => {
    const sx = 6.28, sy = 1.55 + i * 1.3, sw = 3.3, sh = 1.15;
    addCard(s, sx, sy, sw, sh);
    addAccentBar(s, sx, sy, sh);
    s.addText(num,   { x:sx+0.15, y:sy+0.1,  w:sw-0.2, h:0.55, fontSize:36, bold:true, color:BRAND, align:"center", margin:0 });
    s.addText(label, { x:sx+0.15, y:sy+0.68, w:sw-0.2, h:0.22, fontSize:8.5,           color:WHITE, align:"center", margin:0 });
    s.addText(sub,   { x:sx+0.15, y:sy+0.9,  w:sw-0.2, h:0.18, fontSize:7,             color:GRAY2, align:"center", margin:0 });
  });

  // 底部柱状图
  s.addChart(pres.charts.BAR, [{
    name: "指标对比",
    labels: ["本产品", "竞品A", "竞品B", "竞品C"],
    values: [98, 93.1, 91.3, 85.0]
  }], {
    x:0.28, y:3.88, w:5.8, h:1.4, barDir:"col",
    chartColors: [BRAND, "444444", "444444", "333333"],
    chartArea: { fill: { color: CARD } },
    catAxisLabelColor: GRAY2, valAxisLabelColor: GRAY2,
    valGridLine: { color: GRAY3, size: 0.5 }, catGridLine: { style: "none" },
    showValue: true, dataLabelColor: WHITE, dataLabelFontSize: 9, dataLabelPosition: "outEnd",
    showLegend: false, valAxisMinVal: 80,
  });
}

// ---------- SLIDE 5: 成本/数字页（4大数字+3个价格卡）----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Cost / Numbers");
  addSlideTitle(s, "核心数字页标题", "Key Numbers · Cost & Performance");

  // 4个大数字卡
  [["1/20","对比说明","Sub A"],["1/5","对比说明","Sub B"],["3×","速度说明","Sub C"],["2.6×","加速说明","Sub D"]].forEach((c, i) => {
    const cx = 0.28 + i * 2.38, cy = 1.55, cw = 2.2, ch = 1.55;
    s.addShape(pres.shapes.RECTANGLE, { x:cx, y:cy, w:cw, h:ch, fill:{color:i===0?BRAND_DIM:CARD}, line:{color:i===0?BRAND:BORDER,width:i===0?1:0.5}, shadow:makeShadow() });
    addAccentBar(s, cx, cy, ch);
    s.addText(c[0], { x:cx+0.12, y:cy+0.2,  w:cw-0.15, h:0.7,  fontSize:38, bold:true, color:BRAND, align:"center", margin:0 });
    s.addText(c[1], { x:cx+0.12, y:cy+0.95, w:cw-0.15, h:0.28, fontSize:9,             color:WHITE, align:"center", margin:0 });
    s.addText(c[2], { x:cx+0.12, y:cy+1.24, w:cw-0.15, h:0.18, fontSize:7,             color:GRAY2, align:"center", margin:0 });
  });

  // 3个价格/详情卡
  [["小标签A","主要数值1","补充说明文字"],["小标签B","主要数值2","补充说明文字"],["小标签C","主要数值3","补充说明文字"]].forEach((c, i) => {
    const cx = 0.28 + i * 3.22, cy = 3.35, cw = 3.05, ch = 1.9;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    s.addText(c[0], { x:cx+0.18, y:cy+0.18, w:cw-0.25, h:0.22, fontSize:8,  color:GRAY2, charSpacing:2, margin:0 });
    s.addText(c[1], { x:cx+0.18, y:cy+0.5,  w:cw-0.25, h:0.55, fontSize:26, bold:true, color:BRAND, margin:0 });
    s.addText(c[2], { x:cx+0.18, y:cy+1.1,  w:cw-0.25, h:0.28, fontSize:9,             color:GRAY1, margin:0 });
  });
}

// ---------- SLIDE 6: 时间线页 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Timeline / Roadmap");
  addSlideTitle(s, "时间线页标题", "Evolution Timeline · Key Milestones");

  addCard(s, 0.28, 1.55, 9.44, 1.6);
  const tlItems = [
    { year:"2021", name:"里程碑1", desc:"简短描述\n第二行" },
    { year:"2022", name:"里程碑2", desc:"简短描述\n第二行" },
    { year:"2023", name:"里程碑3", desc:"简短描述\n第二行" },
    { year:"2024", name:"里程碑4", desc:"简短描述\n第二行" },
    { year:"2025", name:"里程碑5", desc:"简短描述\n第二行" },
  ];
  tlItems.forEach((item, i) => {
    const tx = 0.75 + i * 1.8;
    s.addShape(pres.shapes.OVAL, { x:tx-0.08, y:2.1, w:0.16, h:0.16, fill:{color:BRAND}, line:{color:BRAND} });
    if (i < tlItems.length-1) s.addShape(pres.shapes.RECTANGLE, { x:tx+0.08, y:2.17, w:1.64, h:0.02, fill:{color:GRAY3}, line:{color:GRAY3} });
    s.addText(item.year, { x:tx-0.5, y:1.68, w:1.3, h:0.2,  fontSize:8,  bold:true, color:BRAND, align:"center", margin:0 });
    s.addText(item.name, { x:tx-0.5, y:2.35, w:1.3, h:0.25, fontSize:10, bold:true, color:WHITE, align:"center", margin:0 });
    s.addText(item.desc, { x:tx-0.5, y:2.62, w:1.3, h:0.42, fontSize:7.5,           color:GRAY1, align:"center", margin:0 });
  });

  // 底部 3 个能力/类别卡
  [["①","分类一","说明文字\n第二行"],["②","分类二","说明文字\n第二行"],["③","分类三","说明文字\n第二行"]].forEach((c, i) => {
    const cx = 0.28 + i * 3.22, cy = 3.38, cw = 3.05, ch = 1.9;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    addIconCircle(s, c[0], cx+0.22, cy+0.25);
    s.addText(c[1], { x:cx+0.82, y:cy+0.28, w:cw-0.9, h:0.35, fontSize:14, bold:true, color:WHITE, margin:0 });
    s.addText(c[2], { x:cx+0.18, y:cy+0.85, w:cw-0.25,h:0.7,  fontSize:9,            color:GRAY1, margin:0 });
  });
}

// ---------- SLIDE 7: 战略/详情页（左英雄卡+右内容）----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, "Strategy / Details");
  addSlideTitle(s, "战略详情页标题", "Strategic Overview · Key Details");

  // 左侧英雄数字卡
  const lx = 0.28, ly = 1.55, lw = 4.2, lh = 3.85;
  s.addShape(pres.shapes.RECTANGLE, { x:lx, y:ly, w:lw, h:lh, fill:{color:BRAND_DIM}, line:{color:BRAND,width:1}, shadow:makeShadow() });
  addAccentBar(s, lx, ly, lh);
  s.addText("小标签",   { x:lx+0.2, y:ly+0.18, w:lw-0.3, h:0.2,  fontSize:8,  color:BRAND, charSpacing:2, margin:0 });
  s.addText("超大数字", { x:lx+0.2, y:ly+0.5,  w:lw-0.3, h:0.8,  fontSize:52, bold:true, color:BRAND, margin:0 });
  s.addText("说明文字", { x:lx+0.2, y:ly+1.35, w:lw-0.3, h:0.28, fontSize:11,           color:GRAY1, margin:0 });
  s.addText("English Subtitle", { x:lx+0.2, y:ly+1.65, w:lw-0.3, h:0.2, fontSize:7.5, color:GRAY2, margin:0 });
  s.addShape(pres.shapes.RECTANGLE, { x:lx+0.2, y:ly+2.0, w:lw-0.4, h:0.02, fill:{color:GRAY3}, line:{color:GRAY3} });

  const rows2 = [["行标签1","数值1"],["行标签2","数值2"],["行标签3","数值3"]];
  rows2.forEach(([k, v], i) => {
    s.addText(k, { x:lx+0.2, y:ly+2.15+i*0.52, w:2,   h:0.28, fontSize:9,  color:GRAY1,  margin:0 });
    s.addText(v, { x:lx+2.2, y:ly+2.15+i*0.52, w:1.8, h:0.28, fontSize:10, bold:true, color:BRAND, align:"right", margin:0 });
  });

  // 右侧：上卡（要点列表）+ 下卡（标签+说明）
  const rx = 4.68, ry = 1.55, rw = 5.04;
  addCard(s, rx, ry, rw, 2.0);
  addAccentBar(s, rx, ry, 2.0);
  s.addText("要点列表标题", { x:rx+0.2, y:ry+0.15, w:rw-0.3, h:0.2, fontSize:7.5, color:GRAY2, charSpacing:2, margin:0 });
  ["要点一：详细描述文字","要点二：详细描述文字","要点三：详细描述文字","要点四：详细描述文字"].forEach((b, i) => {
    s.addShape(pres.shapes.OVAL, { x:rx+0.2, y:ry+0.55+i*0.32, w:0.08, h:0.08, fill:{color:BRAND}, line:{color:BRAND} });
    s.addText(b, { x:rx+0.35, y:ry+0.5+i*0.32, w:rw-0.45, h:0.28, fontSize:9, color:GRAY1, margin:0 });
  });

  addCard(s, rx, ry+2.15, rw, 1.7);
  addAccentBar(s, rx, ry+2.15, 1.7);
  s.addText("标签组标题", { x:rx+0.2, y:ry+2.3, w:rw-0.3, h:0.22, fontSize:7.5, color:GRAY2, charSpacing:2, margin:0 });
  ["标签A","标签B","标签C"].forEach((tag, i) => {
    const tw2 = 1.1, tx3 = rx + 0.2 + i * 1.25;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x:tx3, y:ry+2.65, w:tw2, h:0.3, fill:{color:BRAND_DIM}, line:{color:BRAND,width:0.5}, rectRadius:0.05 });
    s.addText(tag, { x:tx3, y:ry+2.65, w:tw2, h:0.3, fontSize:9, color:BRAND, bold:true, align:"center", margin:0 });
  });
  s.addText("补充说明文字，可以写一两行对上方标签的解释说明。", { x:rx+0.2, y:ry+3.1, w:rw-0.3, h:0.45, fontSize:9, color:GRAY1, margin:0 });
}

// ---------- SLIDE 8: 总结页 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addText("SUMMARY", { x:0.5, y:0.5, w:9, h:0.22, fontSize:8, color:BRAND, bold:true, charSpacing:4, align:"center", margin:0 });
  s.addText([
    { text:"迈向 ",   options:{ color:WHITE } },
    { text:"核心主题", options:{ color:BRAND } },
    { text:" 的",    options:{ color:WHITE } },
  ], { x:0.5, y:0.9, w:9, h:0.8, fontSize:46, bold:true, align:"center", margin:0 });
  s.addText("总结副标题文字", { x:0.5, y:1.68, w:9, h:0.65, fontSize:40, bold:true, color:WHITE, align:"center", margin:0 });
  s.addText("English tagline for the conclusion slide", { x:0.5, y:2.42, w:9, h:0.25, fontSize:10, color:GRAY2, align:"center", margin:0 });

  [["⚡","特点一","说明\n第二行"],["🏆","特点二","说明\n第二行"],["🌐","特点三","说明\n第二行"]].forEach((c, i) => {
    const cx = 1.1 + i * 2.8, cy = 3.0, cw = 2.5, ch = 2.0;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    addIconCircle(s, c[0], cx+0.97, cy+0.2, 0.52);
    s.addText(c[1], { x:cx+0.1, y:cy+0.88, w:cw-0.2, h:0.32, fontSize:14, bold:true, color:WHITE, align:"center", margin:0 });
    s.addText(c[2], { x:cx+0.1, y:cy+1.28, w:cw-0.2, h:0.5,  fontSize:9.5,          color:GRAY1, align:"center", margin:0 });
  });
}

// =============================================
// 💾 输出文件
// =============================================
pres.writeFile({ fileName: "output.pptx" })
  .then(() => console.log("✅ 生成成功: output.pptx"))
  .catch(e => { console.error("❌ 错误:", e); process.exit(1); });
```

---

## 快速开始

```bash
# 运行脚本
ppt-output.js
```

---

## 常用品牌色速查

| 品牌 | BRAND | BRAND_DIM |
|-----|-------|-----------|
| 小米（橙色调） | `FF6900` | `1A0900` |
| 华为（红色调） | `CF0A2C` | `1A0005` |
| 特斯拉（红色调） | `CC0000` | `1A0000` |
| 苹果（蓝色调） | `0071E3` | `001A33` |
| 字节跳动（浅蓝色调） | `006EFF` | `001533` |
| 阿里巴巴（橙色调） | `FF6A00` | `1A0D00` |
| 腾讯（蓝色调） | `12B7F5` | `001A2A` |
| 通用科技蓝 | `00AEEF` | `001A2A` |

---

## 布局尺寸参考（LAYOUT_16x9: 10" × 5.625"）

```
页面宽: 10"    页面高: 5.625"
安全边距: 左右 0.28"，上 0.28"，下 0.2"
标题区域: y=0.28~1.3"（高约1"）
内容区域: y=1.55~5.4"（高约3.85"）

常用卡片高度:
  单行内容: h=0.7~0.9"
  中等内容: h=1.15~1.5"
  大内容:   h=1.8~2.5"
  全高内容: h=3.85"
```
