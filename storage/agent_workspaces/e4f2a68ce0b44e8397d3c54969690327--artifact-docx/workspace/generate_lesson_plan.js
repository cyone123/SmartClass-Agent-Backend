const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, HeadingLevel, 
        AlignmentType, LevelFormat, BorderStyle, WidthType, ShadingType, PageOrientation,
        TableOfContents, PageNumber, Header, Footer } = require('docx');
const fs = require('fs');

const doc = new Document({
  styles: {
    default: { 
      document: { 
        run: { font: "Arial", size: 24 } // 12pt default
      } 
    },
    paragraphStyles: [
      { 
        id: "Heading1", 
        name: "Heading 1", 
        basedOn: "Normal", 
        next: "Normal", 
        quickFormat: true,
        run: { size: 40, bold: true, font: "Arial", color: "2E75B6" },
        paragraph: { spacing: { before: 300, after: 200 }, outlineLevel: 0 }
      },
      { 
        id: "Heading2", 
        name: "Heading 2", 
        basedOn: "Normal", 
        next: "Normal", 
        quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: "1F4E79" },
        paragraph: { spacing: { before: 240, after: 160 }, outlineLevel: 1 }
      },
      { 
        id: "Heading3", 
        name: "Heading 3", 
        basedOn: "Normal", 
        next: "Normal", 
        quickFormat: true,
        run: { size: 28, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 }
      }
    ]
  },
  numbering: {
    config: [
      { 
        reference: "numbers",
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
        reference: "nested-numbers",
        levels: [
          { 
            level: 0, 
            format: LevelFormat.DECIMAL, 
            text: "%1.", 
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } 
          },
          { 
            level: 1, 
            format: LevelFormat.DECIMAL, 
            text: "%1.%2.", 
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 1440, hanging: 360 } } } 
          }
        ] 
      }
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    headers: {
      default: new Header({
        children: [
          new Paragraph({
            children: [
              new TextRun({ 
                text: "牛顿第一定律教学设计方案", 
                bold: true, 
                size: 20,
                color: "2E75B6"
              })
            ],
            alignment: AlignmentType.CENTER
          })
        ]
      })
    },
    footers: {
      default: new Footer({
        children: [
          new Paragraph({
            children: [
              new TextRun({ text: "初三物理 · ", size: 18 }),
              new TextRun({ 
                children: [{ type: PageNumber.CURRENT }], 
                size: 18 
              }),
              new TextRun({ text: " / ", size: 18 }),
              new TextRun({ text: "40 分钟课时", size: 18, italics: true })
            ],
            alignment: AlignmentType.CENTER,
            border: {
              top: { style: BorderStyle.SINGLE, size: 6, color: "2E75B6", space: 1 }
            }
          })
        ]
      })
    },
    children: [
      // Title
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun("牛顿第一定律")]
      }),
      new Paragraph({
        children: [new TextRun({ text: "Newton&#x2019;s First Law", size: 28, italics: true })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 300 }
      }),
      
      // Table of Contents
      new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun("目录")]
      }),
      new TableOfContents("目录", { hyperlink: true, headingStyleRange: "1-3" }),
      new Paragraph({ children: [new TextRun("")], pageBreakBefore: true }),
      
      // Section 1: Basic Information
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun("一、教学基本信息")]
      }),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [3120, 6240],
        rows: [
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3120, type: WidthType.DXA },
                shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "课题", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 6240, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("牛顿第一定律 (Newton&#x2019;s First Law)")] })]
              })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3120, type: WidthType.DXA },
                shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "学科", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 6240, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("物理")] })]
              })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3120, type: WidthType.DXA },
                shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "年级", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 6240, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("初三 (九年级)")] })]
              })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3120, type: WidthType.DXA },
                shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "课时", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 6240, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("1 课时 (40 分钟)")] })]
              })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3120, type: WidthType.DXA },
                shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "课型", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 6240, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("新授课 / 概念规律课")] })]
              })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3120, type: WidthType.DXA },
                shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "教学语言", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 6240, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("中文")] })]
              })
            ]
          })
        ]
      }),
      
      // Section 2: Learning Objectives
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun("二、教学目标")]
      }),
      new Paragraph({
        heading: HeadingLevel.HEADING_3,
        children: [new TextRun("1. 知识与技能")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun("知道牛顿第一定律的内容。")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun("理解惯性的概念，知道惯性是物体固有的属性。")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun("能利用惯性知识解释生活中的简单现象。")]
      }),
      
      new Paragraph({
        heading: HeadingLevel.HEADING_3,
        children: [new TextRun("2. 过程与方法")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun("通过历史回顾，体验&#x201C;理想实验&#x201D;的科学推理方法。")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun("通过实验观察与逻辑推理，纠正&#x201C;力是维持物体运动原因&#x201D;的错误前概念。")]
      }),
      
      new Paragraph({
        heading: HeadingLevel.HEADING_3,
        children: [new TextRun("3. 情感态度与价值观")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun("感受科学探索的艰辛与伟大，培养实事求是的科学态度。")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun("认识到物理知识与生活实际的紧密联系。")]
      }),
      
      // Section 3: Key Points and Difficulties
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun("三、教学重难点")]
      }),
      new Paragraph({
        children: [
          new TextRun({ text: "重点：", bold: true }),
          new TextRun("牛顿第一定律的内容；惯性的概念。")
        ]
      }),
      new Paragraph({
        children: [
          new TextRun({ text: "难点：", bold: true }),
          new TextRun("理解&#x201C;理想实验&#x201D;的推理过程；纠正&#x201C;力是维持物体运动的原因&#x201D;这一错误观念。")
        ]
      }),
      
      // Section 4: Teaching Strategies
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun("四、教学策略与方法")]
      }),
      new Paragraph({
        children: [
          new TextRun({ text: "教学方法：", bold: true }),
          new TextRun("讲授法、探究式教学法、讨论法、演示法。")
        ]
      }),
      new Paragraph({
        children: [
          new TextRun({ text: "所需材料：", bold: true }),
          new TextRun("多媒体课件 (PPT)、斜面小车实验视频/动画、惯性演示器 (可选)、生活实例图片。")
        ]
      }),
      new Paragraph({
        children: [
          new TextRun({ text: "评估方式：", bold: true }),
          new TextRun("课堂提问、实例分析表现、课后作业。")
        ]
      }),
      
      new Paragraph({ children: [new TextRun("")], pageBreakBefore: true }),
      
      // Section 5: Teaching Process
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun("五、教学过程设计 (40 分钟)")]
      }),
      
      // Teaching Process Table
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1200, 800, 2800, 2800, 1760],
        rows: [
          // Header row
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, bottom: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, left: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" }, right: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" } },
                width: { size: 1200, type: WidthType.DXA },
                shading: { fill: "2E75B6", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "环节", bold: true, color: "FFFFFF" })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, bottom: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, left: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" }, right: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" } },
                width: { size: 800, type: WidthType.DXA },
                shading: { fill: "2E75B6", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "时间", bold: true, color: "FFFFFF" })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, bottom: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, left: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" }, right: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" } },
                width: { size: 2800, type: WidthType.DXA },
                shading: { fill: "2E75B6", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "教师活动", bold: true, color: "FFFFFF" })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, bottom: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, left: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" }, right: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" } },
                width: { size: 2800, type: WidthType.DXA },
                shading: { fill: "2E75B6", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "学生活动", bold: true, color: "FFFFFF" })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, bottom: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, left: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" }, right: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" } },
                width: { size: 1760, type: WidthType.DXA },
                shading: { fill: "2E75B6", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "设计意图", bold: true, color: "FFFFFF" })], alignment: AlignmentType.CENTER })]
              })
            ]
          }),
          // Row 1: 情境导入
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1200, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "1. 情境导入", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("5 分钟")], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("展示现象：推箱子，推则动，不推则停。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("提问：亚里士多德认为&#x201C;力是维持运动的原因&#x201D;，对吗？")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("引发认知冲突。")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("观察现象。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("思考并回答直觉看法。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("产生疑问。")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1760, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "利用生活经验引发认知冲突，激发学习兴趣。", italics: true, size: 20 })] })]
              })
            ]
          }),
          // Row 2: 历史回顾与推理
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1200, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "2. 历史回顾与推理", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("10 分钟")], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("介绍伽利略的理想实验。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("播放/演示斜面小车实验动画。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("引导推理：若表面绝对光滑，小车将如何运动？")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("聆听历史背景。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("观察实验现象（阻力越小，滑行越远）。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("跟随逻辑推理得出结论。")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1760, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "突破难点，体验科学推理过程，理解力与运动的真实关系。", italics: true, size: 20 })] })]
              })
            ]
          }),
          // Row 3: 定律建构
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1200, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "3. 定律建构", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("10 分钟")], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("引出牛顿第一定律内容。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("解读关键词：&#x201C;一切&#x201D;、&#x201C;总&#x201D;、&#x201C;或&#x201D;。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("强调：力不是维持运动的原因，而是改变运动状态的原因。")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("齐读定律内容。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("记录笔记。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("理解力与运动的关系。")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1760, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "构建核心概念，明确物理规律。", italics: true, size: 20 })] })]
              })
            ]
          }),
          // Row 4: 惯性概念
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1200, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "4. 惯性概念", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("10 分钟")], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("定义惯性：物体保持原有运动状态不变的性质。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("强调：惯性只与质量有关，与速度无关。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("举例：急刹车、拍打衣服、跳远。")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("理解惯性定义。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("辨析常见误区（如速度大惯性大）。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("尝试解释生活现象。")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1760, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "深化理解，将理论应用于实际，培养解决问题的能力。", italics: true, size: 20 })] })]
              })
            ]
          }),
          // Row 5: 总结与作业
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1200, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "5. 总结与作业", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("5 分钟")], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("课堂小结（思维导图）。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("布置作业：寻找生活中的惯性现象并解释。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("预习下一节。")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("回顾本节课重点。")] }),
                  new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun("记录作业。")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1760, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "巩固知识，延伸学习。", italics: true, size: 20 })] })]
              })
            ]
          })
        ]
      }),
      
      new Paragraph({ children: [new TextRun("")], pageBreakBefore: true }),
      
      // Section 6: Assessment Design
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun("六、教学评估设计")]
      }),
      new Paragraph({
        numbering: { reference: "numbers", level: 0 },
        children: [
          new TextRun({ text: "课堂提问：", bold: true }),
          new TextRun("在历史回顾环节，询问学生&#x201C;如果表面绝对光滑，小车会停吗？&#x201D;")
        ]
      }),
      new Paragraph({
        numbering: { reference: "numbers", level: 0 },
        children: [
          new TextRun({ text: "即时练习：", bold: true }),
          new TextRun("给出一个惯性现象（如泼水），让学生用物理语言解释。")
        ]
      }),
      new Paragraph({
        numbering: { reference: "numbers", level: 0 },
        children: [
          new TextRun({ text: "课后作业：", bold: true }),
          new TextRun("完成配套练习册相关习题，并撰写一篇关于&#x201C;交通安全与惯性&#x201D;的短文。")
        ]
      }),
      
      // Section 7: PPT Outline
      new Paragraph({ children: [new TextRun("")], pageBreakBefore: true }),
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun("七、PPT 课件大纲设计")]
      }),
      new Paragraph({
        children: [
          new TextRun({ text: "设计风格建议：", bold: true }),
          new TextRun("简洁清晰，物理风格（深蓝/白色调），多用图示和动画演示推理过程。")
        ]
      }),
      
      // PPT Table
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1000, 2500, 3800, 2060],
        rows: [
          // Header row
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, bottom: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, left: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" }, right: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" } },
                width: { size: 1000, type: WidthType.DXA },
                shading: { fill: "2E75B6", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "页码", bold: true, color: "FFFFFF" })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, bottom: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, left: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" }, right: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" } },
                width: { size: 2500, type: WidthType.DXA },
                shading: { fill: "2E75B6", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "页面主题", bold: true, color: "FFFFFF" })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, bottom: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, left: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" }, right: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" } },
                width: { size: 3800, type: WidthType.DXA },
                shading: { fill: "2E75B6", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "核心内容/文案", bold: true, color: "FFFFFF" })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, bottom: { style: BorderStyle.SINGLE, size: 2, color: "2E75B6" }, left: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" }, right: { style: BorderStyle.SINGLE, size: 1, color: "2E75B6" } },
                width: { size: 2060, type: WidthType.DXA },
                shading: { fill: "2E75B6", type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "视觉/互动建议", bold: true, color: "FFFFFF" })], alignment: AlignmentType.CENTER })]
              })
            ]
          }),
          // P1
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P1", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "封面", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("标题：牛顿第一定律")] }),
                  new Paragraph({ children: [new TextRun("副标题：力与运动的关系")] }),
                  new Paragraph({ children: [new TextRun("授课人：XXX")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "背景图：牛顿肖像或抽象的运动轨迹", italics: true, size: 20 })] })]
              })
            ]
          }),
          // P2
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P2", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "学习目标", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("1. 知道牛顿第一定律内容")] }),
                  new Paragraph({ children: [new TextRun("2. 理解惯性概念")] }),
                  new Paragraph({ children: [new TextRun("3. 会用惯性解释现象")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "列表展示，清晰明了", italics: true, size: 20 })] })]
              })
            ]
          }),
          // P3
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P3", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "情境思考", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("问题：运动需要力来维持吗？")] }),
                  new Paragraph({ children: [new TextRun("现象：推箱子 -> 动；不推 -> 停。")] }),
                  new Paragraph({ children: [new TextRun("亚里士多德的观点：对吗？")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun({ text: "插入推箱子的 GIF 或图片", italics: true, size: 20 })] }),
                  new Paragraph({ children: [new TextRun({ text: "互动：举手投票（对/错）", italics: true, size: 20 })] })
                ]
              })
            ]
          }),
          // P4
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P4", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "历史回顾：伽利略", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("伽利略的理想实验")] }),
                  new Paragraph({ children: [new TextRun("观点：力不是维持物体运动的原因")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun({ text: "左侧：伽利略画像", italics: true, size: 20 })] }),
                  new Paragraph({ children: [new TextRun({ text: "右侧：斜面实验示意图", italics: true, size: 20 })] })
                ]
              })
            ]
          }),
          // P5
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P5", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "实验推理 (关键页)", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("实验现象：阻力越小，滑行越远。")] }),
                  new Paragraph({ children: [new TextRun("逻辑推理：若阻力为零 -> 永远运动下去。")] }),
                  new Paragraph({ children: [new TextRun("方法：实验 + 推理 (理想实验)")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun({ text: "动画演示：小车在不同表面滑行距离对比", italics: true, size: 20 })] }),
                  new Paragraph({ children: [new TextRun({ text: "重点突出&#x201C;推理&#x201D;二字", italics: true, size: 20, bold: true })] })
                ]
              })
            ]
          }),
          // P6
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P6", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "牛顿第一定律", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("内容：一切物体在没有受到力的作用时，总保持静止状态或匀速直线运动状态。")] }),
                  new Paragraph({ children: [new TextRun("关键词：一切、总、或")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun({ text: "文字加粗高亮", italics: true, size: 20 })] }),
                  new Paragraph({ children: [new TextRun({ text: "配合图示：静止物体 & 匀速直线运动物体", italics: true, size: 20 })] })
                ]
              })
            ]
          }),
          // P7
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P7", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "力与运动的关系", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("纠正误区：")] }),
                  new Paragraph({ children: [new TextRun("❌ 力是维持运动的原因")] }),
                  new Paragraph({ children: [new TextRun("✅ 力是改变物体运动状态的原因")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun({ text: "对比表格形式", italics: true, size: 20 })] }),
                  new Paragraph({ children: [new TextRun({ text: "使用红色叉号和绿色对号", italics: true, size: 20 })] })
                ]
              })
            ]
          }),
          // P8
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P8", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "惯性概念", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("定义：物体保持原有运动状态不变的性质。")] }),
                  new Paragraph({ children: [new TextRun("理解：固有属性，任何物体都有惯性。")] }),
                  new Paragraph({ children: [new TextRun("决定因素：质量 (唯一)")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun({ text: "图示：大卡车 vs 小轿车 (质量大惯性大)", italics: true, size: 20 })] }),
                  new Paragraph({ children: [new TextRun({ text: "强调：与速度无关！", italics: true, size: 20, bold: true })] })
                ]
              })
            ]
          }),
          // P9
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P9", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "生活中的惯性 (1)", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("现象：急刹车时，人为什么向前倾？")] }),
                  new Paragraph({ children: [new TextRun("解释：脚停了，身体由于惯性保持向前运动。")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "插入公交车刹车乘客前倾的图片", italics: true, size: 20 })] })]
              })
            ]
          }),
          // P10
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P10", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "生活中的惯性 (2)", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("现象：拍打衣服除灰、跳远助跑。")] }),
                  new Paragraph({ children: [new TextRun("任务：请同学尝试解释。")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun({ text: "多张生活实例拼图", italics: true, size: 20 })] }),
                  new Paragraph({ children: [new TextRun({ text: "互动：邀请学生回答", italics: true, size: 20 })] })
                ]
              })
            ]
          }),
          // P11
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P11", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "课堂小结", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("1. 牛顿第一定律 (内容)")] }),
                  new Paragraph({ children: [new TextRun("2. 惯性 (定义、影响因素)")] }),
                  new Paragraph({ children: [new TextRun("3. 科学方法 (理想实验)")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "思维导图形式展示", italics: true, size: 20 })] })]
              })
            ]
          }),
          // P12
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P12", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "课后作业", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("1. 完成练习册 Pxx 页")] }),
                  new Paragraph({ children: [new TextRun("2. 思考：安全带为什么要系紧？")] }),
                  new Paragraph({ children: [new TextRun("3. 预习：二力平衡")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "清晰列出作业清单", italics: true, size: 20 })] })]
              })
            ]
          }),
          // P13
          new TableRow({
            children: [
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 1000, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "P13", bold: true })], alignment: AlignmentType.CENTER })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2500, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "结束页", bold: true })] })]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [
                  new Paragraph({ children: [new TextRun("谢谢聆听！")] }),
                  new Paragraph({ children: [new TextRun("物理探索无止境")] })
                ]
              }),
              new TableCell({
                borders: { top: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, left: { style: BorderStyle.SINGLE, size: 1, color: "000000" }, right: { style: BorderStyle.SINGLE, size: 1, color: "000000" } },
                width: { size: 2060, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "简洁致谢", italics: true, size: 20 })] })]
              })
            ]
          })
        ]
      }),
      
      // Section 8: Notes for Next Nodes
      new Paragraph({ children: [new TextRun("")], pageBreakBefore: true }),
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun("八、给后续生成节点的提示")]
      }),
      new Paragraph({
        numbering: { reference: "numbers", level: 0 },
        children: [
          new TextRun({ text: "课件生成：", bold: true }),
          new TextRun("P5 页的&#x201C;理想实验&#x201D;建议生成具体的动画脚本或寻找合适的视频素材链接，这是本课难点。")
        ]
      }),
      new Paragraph({
        numbering: { reference: "numbers", level: 0 },
        children: [
          new TextRun({ text: "互动设计：", bold: true }),
          new TextRun("在 P3 和 P10 页，请设计具体的互动问题框，方便课堂提问。")
        ]
      }),
      new Paragraph({
        numbering: { reference: "numbers", level: 0 },
        children: [
          new TextRun({ text: "教案细化：", bold: true }),
          new TextRun("在生成详细教案时，请为&#x201C;实验推理&#x201D;环节准备具体的引导语（Script），帮助学生跨越思维障碍。")
        ]
      }),
      new Paragraph({
        numbering: { reference: "numbers", level: 0 },
        children: [
          new TextRun({ text: "习题配套：", bold: true }),
          new TextRun("作业部分需配套 3-5 道选择题和 1 道简答题，重点考察惯性只与质量有关这一知识点。")
        ]
      }),
      
      // Footer note
      new Paragraph({ children: [new TextRun("")], pageBreakBefore: true }),
      new Paragraph({
        children: [
          new TextRun({ 
            text: "文档生成时间：", 
            bold: true, 
            italics: true, 
            size: 20,
            color: "666666"
          }),
          new TextRun({ 
            text: new Date().toLocaleDateString('zh-CN'), 
            italics: true, 
            size: 20,
            color: "666666"
          })
        ],
        alignment: AlignmentType.RIGHT
      })
    ]
  }]
});

const path = require('path');
const outputDir = path.join(__dirname, 'AGENT_OUTPUT_DIR');

// Create output directory if it doesn't exist
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

Packer.toBuffer(doc).then(buffer => {
  const outputPath = path.join(outputDir, '牛顿第一定律教学设计方案.docx');
  fs.writeFileSync(outputPath, buffer);
  console.log('Document created successfully at:', outputPath);
}).catch(err => {
  console.error('Error creating document:', err);
  process.exit(1);
});
