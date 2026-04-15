const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, 
        Header, Footer, AlignmentType, BorderStyle, WidthType, 
        ShadingType, VerticalAlign, PageNumber, LevelFormat, HeadingLevel } = require('docx');
const fs = require('fs');

console.log("Starting document generation...");

// 边框样式
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

// 创建表格行
function createRow(label, content, isHeader) {
  return new TableRow({
    children: [
      new TableCell({
        borders: borders,
        width: { size: 2400, type: WidthType.DXA },
        shading: { fill: isHeader ? "2E75B6" : "E7F3FF", type: ShadingType.CLEAR },
        verticalAlign: VerticalAlign.CENTER,
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ 
            text: label, 
            bold: true, 
            font: "Microsoft YaHei",
            color: isHeader ? "FFFFFF" : "2E75B6"
          })]
        })]
      }),
      new TableCell({
        borders: borders,
        width: { size: 6626, type: WidthType.DXA },
        verticalAlign: VerticalAlign.CENTER,
        children: [new Paragraph({
          children: [new TextRun({ text: content, font: "Microsoft YaHei" })]
        })]
      })
    ]
  });
}

try {
  const doc = new Document({
    styles: {
      default: {
        document: { run: { font: "Microsoft YaHei", size: 24 } }
      },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 32, bold: true, font: "Microsoft YaHei", color: "2E75B6" },
          paragraph: { spacing: { before: 300, after: 150 }, outlineLevel: 0 } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 28, bold: true, font: "Microsoft YaHei", color: "404040" },
          paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 1 } },
        { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 26, bold: true, font: "Microsoft YaHei" },
          paragraph: { spacing: { before: 150, after: 80 }, outlineLevel: 2 } }
      ]
    },
    numbering: {
      config: [
        { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
        { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
        { reference: "sub-nums", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "(%1)", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 1080, hanging: 360 } } } }] }
      ]
    },
    sections: [{
      properties: {
        page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } }
      },
      headers: {
        default: new Header({ children: [new Paragraph({
          children: [new TextRun({ text: "初中物理教学设计", font: "Microsoft YaHei", size: 20, color: "808080" })],
          alignment: AlignmentType.RIGHT
        })] })
      },
      footers: {
        default: new Footer({ children: [new Paragraph({
          children: [new TextRun({ text: "第 ", font: "Microsoft YaHei", size: 20 }),
            new TextRun({ children: [PageNumber.CURRENT], font: "Microsoft YaHei", size: 20 }),
            new TextRun({ text: " 页", font: "Microsoft YaHei", size: 20 })],
          alignment: AlignmentType.CENTER
        })] })
      },
      children: [
        // 标题
        new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 300 },
          children: [new TextRun({ text: "牛顿第一定律 教学设计方案", bold: true, font: "Microsoft YaHei", size: 44 })] }),

        // 一、教学概况
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: "一、教学概况", font: "Microsoft YaHei" })] }),
        
        new Table({
          width: { size: 9026, type: WidthType.DXA },
          columnWidths: [2400, 6626],
          rows: [
            createRow("课题", "牛顿第一定律", true),
            createRow("授课对象", "初三学生", false),
            createRow("课时安排", "1课时（40分钟）", false),
            createRow("课型", "新授课/探究课", false),
            createRow("学习目标", "能解决实际问题", false),
            createRow("教学重点", "牛顿第一定律内容的理解；惯性概念的理解", false),
            createRow("教学难点", "对惯性概念的理解与辨析", false),
            createRow("评估方式", "课堂提问", false)
          ]
        }),

        new Paragraph({ children: [] }),

        // 二、教学目标
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: "二、教学目标", font: "Microsoft YaHei" })] }),
        
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: "1. 知识与技能", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "能复述牛顿第一定律的内容，理解一切物体、没有受到外力、总保持的含义。", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "理解惯性是物体的固有属性，知道质量是惯性大小的唯一量度。", font: "Microsoft YaHei" })] }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: "2. 过程与方法", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "通过回顾伽利略理想实验，体会实验+科学推理的研究方法。", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "通过分析生活实例，掌握利用惯性解释现象的逻辑链条。", font: "Microsoft YaHei" })] }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: "3. 情感态度与价值观", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "通过对亚里士多德与伽利略观点的辨析，培养敢于质疑、实事求是的科学态度。", font: "Microsoft YaHei" })] }),

        // 三、教学准备
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: "三、教学准备", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: "教具", font: "Microsoft YaHei" })] }),
        new Paragraph({ children: [new TextRun({ text: "斜面、小车、毛巾、棉布、木板、伽利略理想实验演示视频/动画、惯性演示仪（如惯性小球、木块、小车）。", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: "多媒体", font: "Microsoft YaHei" })] }),
        new Paragraph({ children: [new TextRun({ text: "展示生活实例（绊倒、汽车刹车、锤头松紧等）的PPT或视频片段。", font: "Microsoft YaHei" })] }),

        // 四、教学过程
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: "四、教学过程设计（40分钟）", font: "Microsoft YaHei" })] }),

        // 环节一
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: "环节一：创设情境，激趣导入（3分钟）", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: "活动设计", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 },
          children: [new TextRun({ text: "教师演示：用力推桌子上的粉笔盒，粉笔盒运动；停止推，粉笔盒停止。", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 },
          children: [new TextRun({ text: "提问：物体运动需要力来维持吗？", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: "学生反应", font: "Microsoft YaHei" })] }),
        new Paragraph({ children: [new TextRun({ text: "大部分学生会根据直觉认为需要力（亚里士多德观点）。", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: "教师引导", font: "Microsoft YaHei" })] }),
        new Paragraph({ children: [new TextRun({ text: "引出历史上亚里士多德的观点，并抛出反例——踢出的足球在脚离开后还能继续运动。引出矛盾，进入探究。", font: "Microsoft YaHei" })] }),

        // 环节二
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: "环节二：追溯历史，探究定律（12分钟）", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: "活动设计：伽利略理想实验探究", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 },
          children: [new TextRun({ text: "实验演示：让小车从斜面同一高度滑下，分别滑过铺有毛巾、棉布、木板的水平面。", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 },
          children: [new TextRun({ text: "观察记录：学生观察小车在不同粗糙程度表面滑行的距离。", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 },
          children: [new TextRun({ text: "逻辑推理（师生互动）：", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "sub-nums", level: 0 },
          children: [new TextRun({ text: "提问：为什么在木板上滑得最远？（阻力最小）。", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "sub-nums", level: 0 },
          children: [new TextRun({ text: "提问：如果阻力更小，甚至为零，小车会怎样？（永远运动下去，速度不变）。", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 },
          children: [new TextRun({ text: "得出结论：力不是维持物体运动的原因，而是改变物体运动状态的原因。", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: "定律生成", font: "Microsoft YaHei" })] }),
        new Paragraph({ children: [new TextRun({ text: "展示牛顿第一定律内容：", font: "Microsoft YaHei", bold: true })] }),
        new Paragraph({ children: [new TextRun({ text: "一切物体在没有受到外力作用时，总保持匀速直线运动状态或者静止状态。", font: "Microsoft YaHei", italics: true })] }),
        new Paragraph({ children: [new TextRun({ text: "关键词解析：一切物体、没有受到外力、总保持、或。", font: "Microsoft YaHei" })] }),

        // 环节三
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: "环节三：概念辨析，突破难点（15分钟）", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: "核心概念引入", font: "Microsoft YaHei" })] }),
        new Paragraph({ children: [new TextRun({ text: "一切物体都有保持原有运动状态不变的性质，这种性质叫做惯性。", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: "难点突破策略：通过三个辨析解决惯性概念的理解与辨析", font: "Microsoft YaHei" })] }),
        
        new Paragraph({ children: [new TextRun({ text: "辨析一：惯性与速度有关吗？", font: "Microsoft YaHei", bold: true })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "提问：跑得快的车更难停下，是不是速度大惯性大？", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "纠正：惯性的大小只与质量有关。跑得快难停下是因为动能大，刹车距离长，不是惯性大。", font: "Microsoft YaHei" })] }),
        
        new Paragraph({ children: [new TextRun({ text: "辨析二：惯性是力吗？", font: "Microsoft YaHei", bold: true })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "错题分析：受到惯性的作用、克服惯性。", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "纠正：惯性是性质，不是力。不能说受到惯性力。", font: "Microsoft YaHei" })] }),
        
        new Paragraph({ children: [new TextRun({ text: "辨析三：受力物体有惯性吗？", font: "Microsoft YaHei", bold: true })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "提问：汽车刹车时有惯性，匀速直线运动时有惯性吗？静止时有惯性吗？", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "结论：一切物体在任何状态下都有惯性。", font: "Microsoft YaHei" })] }),

        // 环节四
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: "环节四：联系实际，解决问题（7分钟）", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: "目标达成", font: "Microsoft YaHei" })] }),
        new Paragraph({ children: [new TextRun({ text: "对应能解决实际问题的学习目标。", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: "案例分析", font: "Microsoft YaHei" })] }),
        new Paragraph({ children: [new TextRun({ text: "请学生利用惯性解释生活现象，教师规范答题逻辑。", font: "Microsoft YaHei" })] }),
        new Paragraph({ children: [new TextRun({ text: "现象1：汽车急刹车时人为何前倾？", font: "Microsoft YaHei", bold: true })] }),
        new Paragraph({ children: [new TextRun({ text: "解析模板：人原处于运动状态 - 刹车时脚受力停止 - 上半身由于惯性保持运动 - 向前倾倒。", font: "Microsoft YaHei" })] }),
        new Paragraph({ children: [new TextRun({ text: "现象2：锤头松了，把锤柄在石头上撞击几下，锤头就紧了，为什么？", font: "Microsoft YaHei", bold: true })] }),
        new Paragraph({ children: [new TextRun({ text: "迁移应用：讨论惯性的利用（跳远助跑、拍打灰尘）与防止（系安全带、严禁超载）。", font: "Microsoft YaHei" })] }),

        // 环节五
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: "环节五：总结归纳与评估（3分钟）", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: "知识小结", font: "Microsoft YaHei" })] }),
        new Paragraph({ children: [new TextRun({ text: "牛顿第一定律内容、惯性的定义、惯性与质量的关系。", font: "Microsoft YaHei" })] }),
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: "评估提问", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 },
          children: [new TextRun({ text: "假如地球上的一切物体突然失去惯性，世界会怎样？（检测对维持运动状态的理解）", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 },
          children: [new TextRun({ text: "下列哪个物体的惯性最大？（给出不同质量的物体选项）", font: "Microsoft YaHei" })] }),

        // 五、板书设计
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: "五、板书设计", font: "Microsoft YaHei" })] }),
        
        new Table({
          width: { size: 9026, type: WidthType.DXA },
          columnWidths: [9026],
          rows: [
            new TableRow({
              children: [
                new TableCell({
                  borders: borders,
                  shading: { fill: "F5F5F5", type: ShadingType.CLEAR },
                  children: [
                    new Paragraph({ spacing: { before: 100 }, children: [new TextRun({ text: "牛顿第一定律", bold: true, font: "Microsoft YaHei", size: 26 })] }),
                    new Paragraph({ children: [new TextRun({ text: "", font: "Microsoft YaHei" })] }),
                    new Paragraph({ children: [new TextRun({ text: "一、探究：阻力对运动的影响", bold: true, font: "Microsoft YaHei" })] }),
                    new Paragraph({ indent: { left: 360 }, children: [new TextRun({ text: "实验结论：阻力越小，滑行越远。", font: "Microsoft YaHei" })] }),
                    new Paragraph({ indent: { left: 360 }, children: [new TextRun({ text: "推理：阻力为零，匀速直线运动。", font: "Microsoft YaHei" })] }),
                    new Paragraph({ children: [new TextRun({ text: "", font: "Microsoft YaHei" })] }),
                    new Paragraph({ children: [new TextRun({ text: "二、牛顿第一定律", bold: true, font: "Microsoft YaHei" })] }),
                    new Paragraph({ indent: { left: 360 }, children: [new TextRun({ text: "内容：一切物体...匀速直线运动或静止。", font: "Microsoft YaHei" })] }),
                    new Paragraph({ indent: { left: 360 }, children: [new TextRun({ text: "条件：不受外力。", font: "Microsoft YaHei" })] }),
                    new Paragraph({ children: [new TextRun({ text: "", font: "Microsoft YaHei" })] }),
                    new Paragraph({ children: [new TextRun({ text: "三、惯性（难点）", bold: true, font: "Microsoft YaHei" })] }),
                    new Paragraph({ indent: { left: 360 }, children: [new TextRun({ text: "定义：保持运动状态不变的性质。", font: "Microsoft YaHei" })] }),
                    new Paragraph({ indent: { left: 360 }, children: [new TextRun({ text: "注意：", font: "Microsoft YaHei" })] }),
                    new Paragraph({ indent: { left: 720 }, children: [new TextRun({ text: "1. 一切物体都有惯性。", font: "Microsoft YaHei" })] }),
                    new Paragraph({ indent: { left: 720 }, children: [new TextRun({ text: "2. 惯性大小只与质量有关。", font: "Microsoft YaHei" })] }),
                    new Paragraph({ indent: { left: 720 }, spacing: { after: 100 }, children: [new TextRun({ text: "3. 惯性不是力。", font: "Microsoft YaHei" })] })
                  ]
                })
              ]
            })
          ]
        }),

        // 六、作业布置
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: "六、作业布置", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 },
          children: [new TextRun({ text: "观察并记录生活中的两个惯性现象（一个利用，一个防止），并用物理语言进行解释。", font: "Microsoft YaHei" })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 },
          children: [new TextRun({ text: "思考：如果宇航员在太空中（几乎不受阻力）推一下飞船，飞船会怎样？这体现了什么定律？", font: "Microsoft YaHei" })] }),

        // 设计说明
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: "设计说明", font: "Microsoft YaHei" })] }),
        new Paragraph({ children: [new TextRun({ text: "本方案紧扣初三学生认知水平，利用实验推理突破力与运动关系的认知障碍。针对难点惯性，采用了反例纠错和规范表达的策略，确保学生能正确辨析概念。最后通过生活实例的解析，落实了能解决实际问题的教学目标。", font: "Microsoft YaHei" })] })
      ]
    }]
  });

  // 输出路径
  var outputDir = process.env.AGENT_OUTPUT_DIR || '.';
  var outputPath = outputDir + '/牛顿第一定律_教学设计.docx';

  console.log("Generating document to:", outputPath);

  Packer.toBuffer(doc).then(function(buffer) {
    fs.writeFileSync(outputPath, buffer);
    console.log("教学设计文档已生成: " + outputPath);
  }).catch(function(err) {
    console.error("生成文档时出错:", err);
    process.exit(1);
  });

} catch (e) {
  console.error("Error creating document:", e);
  process.exit(1);
}