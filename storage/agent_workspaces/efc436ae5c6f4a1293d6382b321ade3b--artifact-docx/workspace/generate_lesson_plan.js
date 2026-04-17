const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, 
        AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType, 
        ShadingType, Header, Footer, PageNumber } = require('docx');
const fs = require('fs');

// Get output directory from environment
const outputDir = process.env.AGENT_OUTPUT_DIR || '.';
const outputPath = `${outputDir}/牛顿第一定律_教学设计.docx`;

// Border style for tables
const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const thinBorder = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const headerBorder = { top: thinBorder, bottom: thinBorder, left: thinBorder, right: thinBorder };

// Create the document
const doc = new Document({
  styles: {
    default: { 
      document: { 
        run: { font: "SimSun", size: 24 } // 12pt default, Chinese font
      } 
    },
    paragraphStyles: [
      { 
        id: "Title", 
        name: "Title", 
        basedOn: "Normal", 
        next: "Normal",
        run: { size: 44, bold: true, font: "SimHei" },
        paragraph: { spacing: { before: 200, after: 300 }, alignment: AlignmentType.CENTER }
      },
      { 
        id: "Heading1", 
        name: "Heading 1", 
        basedOn: "Normal", 
        next: "Normal",
        quickFormat: true,
        run: { size: 32, bold: true, font: "SimHei" },
        paragraph: { spacing: { before: 300, after: 150 }, outlineLevel: 0 }
      },
      { 
        id: "Heading2", 
        name: "Heading 2", 
        basedOn: "Normal", 
        next: "Normal",
        quickFormat: true,
        run: { size: 28, bold: true, font: "SimHei" },
        paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 1 }
      },
    ]
  },
  numbering: {
    config: [
      { 
        reference: "objectives",
        levels: [{ 
          level: 0, 
          format: LevelFormat.DECIMAL, 
          text: "%1.", 
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } 
        }]
      },
      { 
        reference: "bullets",
        levels: [{ 
          level: 0, 
          format: LevelFormat.BULLET, 
          text: "•", 
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } 
        }]
      },
      { 
        reference: "steps",
        levels: [{ 
          level: 0, 
          format: LevelFormat.DECIMAL, 
          text: "%1.", 
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } 
        }]
      },
      { 
        reference: "questions",
        levels: [{ 
          level: 0, 
          format: LevelFormat.DECIMAL, 
          text: "%1.", 
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } 
        }]
      },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 }, // A4
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    headers: {
      default: new Header({ 
        children: [new Paragraph({ 
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: "初三物理教学设计", size: 20, color: "666666" })]
        })] 
      })
    },
    footers: {
      default: new Footer({ 
        children: [new Paragraph({ 
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "第 ", size: 20 }), 
            new TextRun({ children: [PageNumber.CURRENT], size: 20 }), 
            new TextRun({ text: " 页", size: 20 })
          ]
        })] 
      })
    },
    children: [
      // Title
      new Paragraph({ 
        heading: HeadingLevel.TITLE,
        children: [new TextRun({ text: "教学设计方案", bold: true, size: 44, font: "SimHei" })]
      }),
      new Paragraph({ 
        alignment: AlignmentType.CENTER,
        spacing: { after: 400 },
        children: [new TextRun({ text: "牛顿第一定律", bold: true, size: 36, font: "SimHei" })]
      }),

      // 一、基本信息
      new Paragraph({ 
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun({ text: "一、基本信息", bold: true, size: 32, font: "SimHei" })]
      }),
      
      // Basic info table
      new Table({
        width: { size: 9026, type: WidthType.DXA },
        columnWidths: [2256, 2256, 2256, 2256],
        rows: [
          new TableRow({
            children: [
              createCell("课程名称", true, 2256),
              createCell("牛顿第一定律", false, 2256),
              createCell("适用年级", true, 2256),
              createCell("初三", false, 2256),
            ]
          }),
          new TableRow({
            children: [
              createCell("学科", true, 2256),
              createCell("物理", false, 2256),
              createCell("课时安排", true, 2256),
              createCell("1课时（40分钟）", false, 2256),
            ]
          }),
          new TableRow({
            children: [
              createCell("教学方法", true, 2256),
              createCell("实验探究法", false, 2256),
              createCell("教学用具", true, 2256),
              createCell("斜面、小车、毛巾、棉布、木板、刻度尺、多媒体课件", false, 2256),
            ]
          }),
        ]
      }),

      // 二、教学目标
      new Paragraph({ 
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun({ text: "二、教学目标", bold: true, size: 32, font: "SimHei" })]
      }),

      new Paragraph({ 
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun({ text: "1. 知识与技能", bold: true, size: 28, font: "SimHei" })]
      }),
      new Paragraph({ 
        numbering: { reference: "objectives", level: 0 },
        children: [new TextRun({ text: "理解牛顿第一定律的内容，能够复述定律并解释\u201C一切\u201D、\u201C没有受到外力\u201D、\u201C总保持\u201D等关键词的含义。", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "objectives", level: 0 },
        children: [new TextRun({ text: "理解惯性是物体的固有属性，知道质量是惯性大小的量度。", size: 24 })]
      }),

      new Paragraph({ 
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun({ text: "2. 过程与方法", bold: true, size: 28, font: "SimHei" })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "通过\u201C斜面小车\u201D实验，体验\u201C控制变量法\u201D和\u201C科学推理法\u201D（理想实验法）在物理探究中的应用。", size: 24 })]
      }),

      new Paragraph({ 
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun({ text: "3. 情感态度与价值观", bold: true, size: 28, font: "SimHei" })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "通过对亚里士多德与伽利略观点的辨析，培养敢于质疑、实事求是的科学态度。", size: 24 })]
      }),

      // 三、教学重难点
      new Paragraph({ 
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun({ text: "三、教学重难点", bold: true, size: 32, font: "SimHei" })]
      }),
      
      new Paragraph({ 
        spacing: { before: 100 },
        children: [
          new TextRun({ text: "【重点】", bold: true, size: 24, font: "SimHei" }),
          new TextRun({ text: "牛顿第一定律的建立过程及内容理解。", size: 24 })
        ]
      }),
      new Paragraph({ 
        spacing: { before: 100 },
        children: [
          new TextRun({ text: "【难点】", bold: true, size: 24, font: "SimHei" }),
          new TextRun({ text: "对惯性概念的理解与辨析（特别是\u201C物体运动状态改变与惯性无关\u201D这一认知误区的突破）。", size: 24 })
        ]
      }),

      // 四、教学过程设计
      new Paragraph({ 
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun({ text: "四、教学过程设计", bold: true, size: 32, font: "SimHei" })]
      }),

      // 环节一
      new Paragraph({ 
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun({ text: "环节一：情境导入与认知冲突（5分钟）", bold: true, size: 28, font: "SimHei" })]
      }),
      new Paragraph({ 
        spacing: { before: 100 },
        children: [new TextRun({ text: "【活动设计】", bold: true, size: 24, font: "SimHei" })]
      }),
      new Paragraph({ 
        numbering: { reference: "steps", level: 0 },
        children: [new TextRun({ text: "教师演示：用力推讲台上的粉笔盒，它运动；停止推力，它静止。", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "steps", level: 0 },
        children: [new TextRun({ text: "提问：\u201C物体的运动需要力来维持吗？\u201D", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "steps", level: 0 },
        children: [new TextRun({ text: "引导学生联想生活经验（如推车、踢球），大部分学生会直觉认同亚里士多德的观点：\u201C力是维持物体运动的原因\u201D。", size: 24 })]
      }),
      new Paragraph({ 
        spacing: { before: 100 },
        children: [
          new TextRun({ text: "【教师引导】", bold: true, size: 24, font: "SimHei" }),
          new TextRun({ text: "展示亚里士多德与伽利略的观点对比，指出直觉往往是不可靠的，引入\u201C实验探究\u201D来验证。", size: 24 })
        ]
      }),

      // 环节二
      new Paragraph({ 
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun({ text: "环节二：实验探究——牛顿第一定律的建立（15分钟）", bold: true, size: 28, font: "SimHei" })]
      }),
      new Paragraph({ 
        spacing: { before: 100 },
        children: [new TextRun({ text: "【实验操作】", bold: true, size: 24, font: "SimHei" })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "使用斜面小车装置。", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "控制变量：让小车从斜面同一高度滑下（控制初速度相同）。", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "改变条件：分别在毛巾表面、棉布表面、木板表面滑行。", size: 24 })]
      }),
      
      new Paragraph({ 
        spacing: { before: 150 },
        children: [new TextRun({ text: "【观察记录】", bold: true, size: 24, font: "SimHei" })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "引导学生观察小车在不同表面滑行的距离，并记录在表格中。", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "数据分析：阻力越小，滑行距离越远，速度减小得越慢。", size: 24 })]
      }),

      new Paragraph({ 
        spacing: { before: 150 },
        children: [new TextRun({ text: "【科学推理】（关键步骤）", bold: true, size: 24, font: "SimHei" })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "提问：\u201C如果木板绝对光滑（没有阻力），小车将运动多远？\u201D", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "推理结论：小车将永远运动下去，做匀速直线运动。", size: 24 })]
      }),

      new Paragraph({ 
        spacing: { before: 150 },
        children: [new TextRun({ text: "【总结定律】", bold: true, size: 24, font: "SimHei" })]
      }),
      new Paragraph({ 
        spacing: { before: 100 },
        children: [new TextRun({ text: "综合伽利略、笛卡尔、牛顿的研究，引出牛顿第一定律：", size: 24 })]
      }),
      new Paragraph({ 
        alignment: AlignmentType.CENTER,
        spacing: { before: 100, after: 100 },
        shading: { fill: "E8F4E8", type: ShadingType.CLEAR },
        children: [new TextRun({ text: "一切物体在没有受到外力作用时，总保持静止状态或匀速直线运动状态。", bold: true, size: 24, font: "SimHei" })]
      }),

      // 环节三
      new Paragraph({ 
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun({ text: "环节三：难点突破——惯性的理解与应用（15分钟）", bold: true, size: 28, font: "SimHei" })]
      }),
      new Paragraph({ 
        spacing: { before: 100 },
        children: [new TextRun({ text: "【概念界定】", bold: true, size: 24, font: "SimHei" })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "定律引申：物体保持运动状态不变的性质叫做惯性。", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "强调：惯性是物体的固有属性，一切物体在任何情况下（无论运动、静止、受力、不受力）都有惯性。", size: 24 })]
      }),

      new Paragraph({ 
        spacing: { before: 150 },
        children: [new TextRun({ text: "【互动辨析】（难点攻克）", bold: true, size: 24, font: "SimHei" })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "提问：\u201C高速行驶的汽车刹车时有惯性，静止时有没有惯性？\u201D", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "纠错：纠正\u201C物体运动越快惯性越大\u201D的错误观点（惯性只与质量有关）。", size: 24 })]
      }),

      new Paragraph({ 
        spacing: { before: 150 },
        children: [new TextRun({ text: "【实际问题解决】（达成教学目标）", bold: true, size: 24, font: "SimHei" })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [
          new TextRun({ text: "案例1：", bold: true, size: 24 }),
          new TextRun({ text: "为什么锤头松了，把锤柄在地上撞几下就紧了？（解释：锤柄受力停止，锤头由于惯性继续向下运动，套紧。）", size: 24 })
        ]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [
          new TextRun({ text: "案例2：", bold: true, size: 24 }),
          new TextRun({ text: "为什么跳远运动员起跳前要助跑？（解释：利用惯性保持向前的速度。）", size: 24 })
        ]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [
          new TextRun({ text: "案例3：", bold: true, size: 24 }),
          new TextRun({ text: "交通安全中的系安全带是为了防止什么？（解释：防止急刹车时人由于惯性向前倾倒造成伤害。）", size: 24 })
        ]
      }),

      new Paragraph({ 
        spacing: { before: 150 },
        children: [new TextRun({ text: "【方法总结】", bold: true, size: 24, font: "SimHei" })]
      }),
      new Paragraph({ 
        children: [new TextRun({ text: "引导学生总结解释惯性现象的三步法：", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "确认原状态；", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "指出受力物体运动状态改变；", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "另一物体由于惯性保持原状态。", size: 24 })]
      }),

      // 环节四
      new Paragraph({ 
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun({ text: "环节四：课堂小结与评估（5分钟）", bold: true, size: 28, font: "SimHei" })]
      }),
      new Paragraph({ 
        spacing: { before: 100 },
        children: [new TextRun({ text: "【知识梳理】", bold: true, size: 24, font: "SimHei" })]
      }),
      new Paragraph({ 
        children: [new TextRun({ text: "回顾力的作用（改变运动状态而非维持运动）、牛顿第一定律内容、惯性概念。", size: 24 })]
      }),

      new Paragraph({ 
        spacing: { before: 150 },
        children: [new TextRun({ text: "【课堂提问评估】", bold: true, size: 24, font: "SimHei" })]
      }),
      new Paragraph({ 
        numbering: { reference: "questions", level: 0 },
        children: [new TextRun({ text: "\u201C牛顿第一定律是通过实验直接得出的吗？\u201D（考查科学方法）", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "questions", level: 0 },
        children: [new TextRun({ text: "\u201C把衣服抖一下，灰尘为什么掉落？\u201D（考查实际应用能力）", size: 24 })]
      }),
      new Paragraph({ 
        numbering: { reference: "questions", level: 0 },
        children: [new TextRun({ text: "\u201C如果物体受力平衡，它会保持什么状态？\u201D（为下一节二力平衡做铺垫）", size: 24 })]
      }),

      // 五、板书设计
      new Paragraph({ 
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun({ text: "五、板书设计", bold: true, size: 32, font: "SimHei" })]
      }),

      // Blackboard design table
      new Table({
        width: { size: 9026, type: WidthType.DXA },
        columnWidths: [9026],
        rows: [
          new TableRow({
            children: [
              new TableCell({
                borders: { top: thinBorder, bottom: thinBorder, left: thinBorder, right: thinBorder },
                width: { size: 9026, type: WidthType.DXA },
                shading: { fill: "F5F5F5", type: ShadingType.CLEAR },
                children: [
                  new Paragraph({ 
                    alignment: AlignmentType.CENTER,
                    spacing: { before: 150, after: 100 },
                    children: [new TextRun({ text: "牛顿第一定律", bold: true, size: 28, font: "SimHei" })]
                  }),
                  new Paragraph({ 
                    spacing: { before: 100 },
                    children: [new TextRun({ text: "1. 历史观点：", bold: true, size: 24, font: "SimHei" })]
                  }),
                  new Paragraph({ 
                    indent: { left: 360 },
                    children: [new TextRun({ text: "• 亚里士多德：力是维持运动的原因（错）", size: 24 })]
                  }),
                  new Paragraph({ 
                    indent: { left: 360 },
                    children: [new TextRun({ text: "• 伽利略：力是改变运动状态的原因（对）", size: 24 })]
                  }),
                  new Paragraph({ 
                    spacing: { before: 100 },
                    children: [new TextRun({ text: "2. 牛顿第一定律：", bold: true, size: 24, font: "SimHei" })]
                  }),
                  new Paragraph({ 
                    indent: { left: 360 },
                    children: [new TextRun({ text: "• 内容：一切物体...静止或匀速直线运动。", size: 24 })]
                  }),
                  new Paragraph({ 
                    indent: { left: 360 },
                    children: [new TextRun({ text: "• 方法：实验 + 科学推理（理想实验法）。", size: 24 })]
                  }),
                  new Paragraph({ 
                    spacing: { before: 100 },
                    children: [new TextRun({ text: "3. 惯性：", bold: true, size: 24, font: "SimHei" })]
                  }),
                  new Paragraph({ 
                    indent: { left: 360 },
                    children: [new TextRun({ text: "• 定义：保持状态不变的性质。", size: 24 })]
                  }),
                  new Paragraph({ 
                    indent: { left: 360 },
                    spacing: { after: 150 },
                    children: [new TextRun({ text: "• 决定因素：质量（与速度、受力无关）。", size: 24 })]
                  }),
                ]
              })
            ]
          })
        ]
      }),

      // 六、教学设计说明
      new Paragraph({ 
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun({ text: "六、教学设计说明", bold: true, size: 32, font: "SimHei" })]
      }),
      new Paragraph({ 
        spacing: { before: 100 },
        indent: { firstLine: 480 },
        children: [new TextRun({ text: "本设计严格遵循\u201C实验探究法\u201D，利用斜面小车实验让学生经历从感性认识到理性推理的过程，有效解决了学生对\u201C力与运动关系\u201D的认知偏差。针对\u201C惯性\u201D这一难点，特意安排了概念辨析和生活实例应用环节，确保达成\u201C能解决实际问题\u201D的学习目标。", size: 24 })]
      }),
    ]
  }]
});

// Helper function to create table cells
function createCell(text, isHeader, width) {
  const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
  return new TableCell({
    borders: { top: border, bottom: border, left: border, right: border },
    width: { size: width, type: WidthType.DXA },
    shading: isHeader ? { fill: "E6F2FF", type: ShadingType.CLEAR } : undefined,
    children: [new Paragraph({ 
      alignment: isHeader ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [new TextRun({ 
        text: text, 
        bold: isHeader, 
        size: 24,
        font: isHeader ? "SimHei" : "SimSun"
      })] 
    })]
  });
}

// Generate the document
Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(outputPath, buffer);
  console.log(`Document generated successfully: ${outputPath}`);
}).catch(err => {
  console.error('Error generating document:', err);
  process.exit(1);
});