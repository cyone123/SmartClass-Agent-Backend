const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

// 读取内容数据
const content = JSON.parse(fs.readFileSync(path.join(__dirname, "lesson-content.json"), "utf-8"));

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = content.title;

// =============================================
// 🎨 设计系统 — 物理课主题色（科技蓝）
// =============================================
const BG     = "0A1F3D"; // 深蓝背景
const CARD   = "122B4F";
const CARD2  = "1A3A66";
const WHITE  = "FFFFFF";
const GRAY1  = "CCCCCC";
const GRAY2  = "999999";
const GRAY3  = "444444";
const BORDER = "2A4A7A";

// 科技蓝品牌色
const BRAND     = "00AEEF";   // 亮蓝
const BRAND_DIM = "001A2A";   // 暗蓝

// makeShadow 必须是函数，每次调用返回新对象
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

// 品牌色左侧细竖条
function addAccentBar(slide, x, y, h) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 0.06, h,
    fill: { color: BRAND }, line: { color: BRAND }
  });
}

// 版块小标签
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

// 图标圆圈
function addIconCircle(slide, icon, x, y, size=0.45) {
  slide.addShape(pres.shapes.OVAL, {
    x, y, w:size, h:size,
    fill: { color: BRAND_DIM }, line: { color: BRAND, width: 0.5 }
  });
  slide.addText(icon, { x, y, w:size, h:size, fontSize:size*22, align:"center", valign:"middle", margin:0 });
}

// 获取输出目录（兼容环境变量）
const outputDir = process.env.AGENT_OUTPUT_DIR || "output/";
const outputPath = path.join(outputDir, "牛顿第一定律教学课件.pptx");

// =============================================
// 📑 生成幻灯片
// =============================================

// ---------- SLIDE 1: 封面 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addText(`${content.author} · ${content.title} · ${content.date}`, { 
    x:0.5, y:0.38, w:6, h:0.2, fontSize:7, color:GRAY2, charSpacing:4, margin:0 
  });

  s.addText([
    { text: "牛顿", options: { color: BRAND, bold: true } },
    { text: "第一定律", options: { color: WHITE, bold: true } }
  ], { x:0.5, y:0.85, w:6, h:1.0, fontSize:52, margin:0 });

  s.addText(content.subtitle, { x:0.5, y:2.6, w:6, h:0.3, fontSize:13, color:GRAY1, margin:0 });

  s.addShape(pres.shapes.RECTANGLE, { x:0.5, y:3.1, w:1.2, h:0.04, fill:{ color:BRAND }, line:{ color:BRAND } });

  // 底部 meta 数据
  const meta = content.slides[0].meta;
  meta.forEach(({value, label}, i) => {
    const bx = 0.5 + i * 1.5;
    addCard(s, bx, 3.3, 1.3, 0.72);
    s.addText(value, { x:bx, y:3.33, w:1.3, h:0.3,  fontSize:18, bold:true, color:BRAND, align:"center", margin:0 });
    s.addText(label, { x:bx, y:3.65, w:1.3, h:0.18, fontSize:7,            color:GRAY2, align:"center", margin:0 });
  });

  // 右侧科学家卡片
  const rightCards = content.slides[0].rightCards;
  rightCards.forEach(({value, desc}, i) => {
    addCard(s, 7.0, 0.6 + i * 1.55, 2.6, 1.3);
    addAccentBar(s, 7.0, 0.6 + i * 1.55, 1.3);
    s.addText(value, { x:7.1, y:0.6+i*1.55+0.22, w:2.4, h:0.45, fontSize:22, bold:true, color:BRAND, align:"center", margin:0 });
    s.addText(desc, { x:7.1, y:0.6+i*1.55+0.7,  w:2.4, h:0.22, fontSize:8,            color:GRAY2, align:"center", margin:0 });
  });
}

// ---------- SLIDE 2: 经验误区（三列矩阵）----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, content.slides[1].sectionLabel);
  addSlideTitle(s, content.slides[1].title, content.slides[1].subtitle);

  const cards = content.slides[1].cards;
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

// ---------- SLIDE 3: 实验探究（2×2 内容卡）----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, content.slides[2].sectionLabel);
  addSlideTitle(s, content.slides[2].title, content.slides[2].subtitle);

  const items = content.slides[2].items;
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

// ---------- SLIDE 4: 科学推理（左表+右数字卡）----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, content.slides[3].sectionLabel);
  addSlideTitle(s, content.slides[3].title, content.slides[3].subtitle);

  // 左侧表格
  const tx = 0.28, ty = 1.55, tw = 5.8, th = 3.85;
  addCard(s, tx, ty, tw, th);
  s.addText("实验数据与推理", { x:tx+0.2, y:ty+0.15, w:5, h:0.2, fontSize:8, color:GRAY2, charSpacing:2, margin:0 });

  const headers = content.slides[3].tableData.headers;
  const colXs   = [tx+0.2, tx+2.0, tx+3.3, tx+4.6];
  headers.forEach((h, i) => s.addText(h, { x:colXs[i], y:ty+0.45, w:1.2, h:0.22, fontSize:8, color:GRAY2, bold:true, margin:0 }));
  s.addShape(pres.shapes.RECTANGLE, { x:tx+0.1, y:ty+0.7, w:tw-0.2, h:0.02, fill:{color:GRAY3}, line:{color:GRAY3} });

  const rows = content.slides[3].tableData.rows;
  rows.forEach((row, ri) => {
    const ry = ty + 0.82 + ri * 0.72;
    s.addText(row.name, { x:colXs[0], y:ry, w:1.7, h:0.28, fontSize:ri===rows.length-1?10:9, bold:ri===rows.length-1, color:ri===rows.length-1?BRAND:GRAY1, margin:0 });
    row.vals.forEach((v, vi) => s.addText(v, { x:colXs[vi+1], y:ry, w:1.2, h:0.28, fontSize:10, bold:ri===rows.length-1, color:ri===rows.length-1?BRAND:GRAY2, margin:0 }));
    if (ri < rows.length-1) s.addShape(pres.shapes.RECTANGLE, { x:tx+0.1, y:ry+0.36, w:tw-0.2, h:0.01, fill:{color:GRAY3}, line:{color:GRAY3} });
  });

  // 右侧大数字卡
  const bigNumbers = content.slides[3].bigNumbers;
  bigNumbers.forEach(({num, label, sub}, i) => {
    const sx = 6.28, sy = 1.55 + i * 1.3, sw = 3.3, sh = 1.15;
    addCard(s, sx, sy, sw, sh);
    addAccentBar(s, sx, sy, sh);
    s.addText(num,   { x:sx+0.15, y:sy+0.1,  w:sw-0.2, h:0.55, fontSize:36, bold:true, color:BRAND, align:"center", margin:0 });
    s.addText(label, { x:sx+0.15, y:sy+0.68, w:sw-0.2, h:0.22, fontSize:8.5,           color:WHITE, align:"center", margin:0 });
    s.addText(sub,   { x:sx+0.15, y:sy+0.9,  w:sw-0.2, h:0.18, fontSize:7,             color:GRAY2, align:"center", margin:0 });
  });
}

// ---------- SLIDE 5: 定律建立（4大数字+3个价格卡）----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, content.slides[4].sectionLabel);
  addSlideTitle(s, content.slides[4].title, content.slides[4].subtitle);

  // 4个大数字卡
  const bigNumbers = content.slides[4].bigNumbers;
  bigNumbers.forEach((c, i) => {
    const cx = 0.28 + i * 2.38, cy = 1.55, cw = 2.2, ch = 1.55;
    s.addShape(pres.shapes.RECTANGLE, { 
      x:cx, y:cy, w:cw, h:ch, 
      fill:{color:i===3?BRAND_DIM:CARD}, 
      line:{color:i===3?BRAND:BORDER,width:i===3?1:0.5}, 
      shadow:makeShadow() 
    });
    addAccentBar(s, cx, cy, ch);
    s.addText(c.num, { x:cx+0.12, y:cy+0.2,  w:cw-0.15, h:0.7,  fontSize:38, bold:true, color:BRAND, align:"center", margin:0 });
    s.addText(c.label, { x:cx+0.12, y:cy+0.95, w:cw-0.15, h:0.28, fontSize:9,             color:WHITE, align:"center", margin:0 });
    s.addText(c.sub, { x:cx+0.12, y:cy+1.24, w:cw-0.15, h:0.18, fontSize:7,             color:GRAY2, align:"center", margin:0 });
  });

  // 3个价格/详情卡
  const priceCards = content.slides[4].priceCards;
  priceCards.forEach((c, i) => {
    const cx = 0.28 + i * 3.22, cy = 3.35, cw = 3.05, ch = 1.9;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    s.addText(c.tag, { x:cx+0.18, y:cy+0.18, w:cw-0.25, h:0.22, fontSize:8,  color:GRAY2, charSpacing:2, margin:0 });
    s.addText(c.value, { x:cx+0.18, y:cy+0.5,  w:cw-0.25, h:0.55, fontSize:26, bold:true, color:BRAND, margin:0 });
    s.addText(c.desc, { x:cx+0.18, y:cy+1.1,  w:cw-0.25, h:0.28, fontSize:9,             color:GRAY1, margin:0 });
  });
}

// ---------- SLIDE 6: 生活应用（时间线+分类卡）----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, content.slides[5].sectionLabel);
  addSlideTitle(s, content.slides[5].title, content.slides[5].subtitle);

  addCard(s, 0.28, 1.55, 9.44, 1.6);
  const tlItems = content.slides[5].timeline;
  tlItems.forEach((item, i) => {
    const tx = 0.75 + i * 1.8;
    s.addShape(pres.shapes.OVAL, { x:tx-0.08, y:2.1, w:0.16, h:0.16, fill:{color:BRAND}, line:{color:BRAND} });
    if (i < tlItems.length-1) s.addShape(pres.shapes.RECTANGLE, { x:tx+0.08, y:2.17, w:1.64, h:0.02, fill:{color:GRAY3}, line:{color:GRAY3} });
    s.addText(item.year, { x:tx-0.5, y:1.68, w:1.3, h:0.2,  fontSize:8,  bold:true, color:BRAND, align:"center", margin:0 });
    s.addText(item.name, { x:tx-0.5, y:2.35, w:1.3, h:0.25, fontSize:10, bold:true, color:WHITE, align:"center", margin:0 });
    s.addText(item.desc, { x:tx-0.5, y:2.62, w:1.3, h:0.42, fontSize:7.5,           color:GRAY1, align:"center", margin:0 });
  });

  // 底部分类卡
  const categoryCards = content.slides[5].categoryCards;
  categoryCards.forEach((c, i) => {
    const cx = 0.28 + i * 3.22, cy = 3.38, cw = 3.05, ch = 1.9;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    addIconCircle(s, c.icon, cx+0.22, cy+0.25);
    s.addText(c.name, { x:cx+0.82, y:cy+0.28, w:cw-0.9, h:0.35, fontSize:14, bold:true, color:WHITE, margin:0 });
    s.addText(c.desc, { x:cx+0.18, y:cy+0.85, w:cw-0.25,h:0.7,  fontSize:9,            color:GRAY1, margin:0 });
  });
}

// ---------- SLIDE 7: 核心总结（战略页）----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  addSectionLabel(s, content.slides[6].sectionLabel);
  addSlideTitle(s, content.slides[6].title, content.slides[6].subtitle);

  // 左侧英雄卡
  const hero = content.slides[6].heroCard;
  const lx = 0.28, ly = 1.55, lw = 4.2, lh = 3.85;
  s.addShape(pres.shapes.RECTANGLE, { 
    x:lx, y:ly, w:lw, h:lh, 
    fill:{color:BRAND_DIM}, 
    line:{color:BRAND,width:1}, 
    shadow:makeShadow() 
  });
  addAccentBar(s, lx, ly, lh);
  s.addText(hero.tag, { x:lx+0.2, y:ly+0.18, w:lw-0.3, h:0.2,  fontSize:8,  color:BRAND, charSpacing:2, margin:0 });
  s.addText(hero.bigNumber, { x:lx+0.2, y:ly+0.5,  w:lw-0.3, h:0.8,  fontSize:24, bold:true, color:BRAND, margin:0 });
  s.addText(hero.desc, { x:lx+0.2, y:ly+1.35, w:lw-0.3, h:0.28, fontSize:11,           color:GRAY1, margin:0 });
  s.addText(hero.english, { x:lx+0.2, y:ly+1.65, w:lw-0.3, h:0.2, fontSize:7.5, color:GRAY2, margin:0 });
  s.addShape(pres.shapes.RECTANGLE, { x:lx+0.2, y:ly+2.0, w:lw-0.4, h:0.02, fill:{color:GRAY3}, line:{color:GRAY3} });

  hero.rows.map(item => [item.key, item.value])
  .forEach(([k, v], i) => {
    s.addText(k, { x:lx+0.2, y:ly+2.15+i*0.52, w:2,   h:0.28, fontSize:9,  color:GRAY1,  margin:0 });
    s.addText(v, { x:lx+2.2, y:ly+2.15+i*0.52, w:1.8, h:0.28, fontSize:10, bold:true, color:BRAND, align:"right", margin:0 });
  });

  // 右侧上：误区辨析
  const rightTop = content.slides[6].rightTop;
  const rx = 4.68, ry = 1.55, rw = 5.04;
  addCard(s, rx, ry, rw, 2.0);
  addAccentBar(s, rx, ry, 2.0);
  s.addText(rightTop.title, { x:rx+0.2, y:ry+0.15, w:rw-0.3, h:0.2, fontSize:7.5, color:GRAY2, charSpacing:2, margin:0 });
  rightTop.bullets.forEach((b, i) => {
    s.addShape(pres.shapes.OVAL, { x:rx+0.2, y:ry+0.55+i*0.32, w:0.08, h:0.08, fill:{color:BRAND}, line:{color:BRAND} });
    s.addText(b, { x:rx+0.35, y:ry+0.5+i*0.32, w:rw-0.45, h:0.28, fontSize:9, color:GRAY1, margin:0 });
  });

  // 右侧下：科学方法
  const rightBottom = content.slides[6].rightBottom;
  addCard(s, rx, ry+2.15, rw, 1.7);
  addAccentBar(s, rx, ry+2.15, 1.7);
  s.addText(rightBottom.tagTitle, { x:rx+0.2, y:ry+2.3, w:rw-0.3, h:0.22, fontSize:7.5, color:GRAY2, charSpacing:2, margin:0 });
  rightBottom.tags.forEach((tag, i) => {
    const tw2 = 1.1, tx3 = rx + 0.2 + i * 1.25;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x:tx3, y:ry+2.65, w:tw2, h:0.3, fill:{color:BRAND_DIM}, line:{color:BRAND,width:0.5}, rectRadius:0.05 });
    s.addText(tag, { x:tx3, y:ry+2.65, w:tw2, h:0.3, fontSize:9, color:BRAND, bold:true, align:"center", margin:0 });
  });
  s.addText(rightBottom.desc, { x:rx+0.2, y:ry+3.1, w:rw-0.3, h:0.45, fontSize:9, color:GRAY1, margin:0 });
}

// ---------- SLIDE 8: 总结页 ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addText(content.slides[7].sectionLabel, { 
    x:0.5, y:0.5, w:9, h:0.22, fontSize:8, color:BRAND, bold:true, charSpacing:4, align:"center", margin:0 
  });
  s.addText([
    { text: content.slides[7].title, options:{ color:WHITE } },
    { text: content.slides[7].highlight, options:{ color:BRAND } },
    { text: content.slides[7].suffix, options:{ color:WHITE } }
  ], { x:0.5, y:0.9, w:9, h:0.8, fontSize:46, bold:true, align:"center", margin:0 });
  s.addText(content.slides[7].subtitle, { x:0.5, y:1.68, w:9, h:0.65, fontSize:40, bold:true, color:WHITE, align:"center", margin:0 });
  s.addText(content.slides[7].tagline, { x:0.5, y:2.42, w:9, h:0.25, fontSize:10, color:GRAY2, align:"center", margin:0 });

  const features = content.slides[7].features;
  features.forEach((c, i) => {
    const cx = 1.1 + i * 2.8, cy = 3.0, cw = 2.5, ch = 2.0;
    addCard(s, cx, cy, cw, ch);
    addAccentBar(s, cx, cy, ch);
    addIconCircle(s, c.icon, cx+0.97, cy+0.2, 0.52);
    s.addText(c.name, { x:cx+0.1, y:cy+0.88, w:cw-0.2, h:0.32, fontSize:14, bold:true, color:WHITE, align:"center", margin:0 });
    s.addText(c.desc, { x:cx+0.1, y:cy+1.28, w:cw-0.2, h:0.5,  fontSize:9.5,          color:GRAY1, align:"center", margin:0 });
  });
}

// =============================================
// 💾 输出文件
// =============================================
pres.writeFile({ fileName: outputPath })
  .then(() => console.log(`✅ 生成成功: ${outputPath}`))
  .catch(e => { console.error("❌ 错误:", e); process.exit(1); });