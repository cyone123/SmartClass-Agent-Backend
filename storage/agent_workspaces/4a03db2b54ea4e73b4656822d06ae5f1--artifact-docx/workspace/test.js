console.log("Test started");
try {
  const docx = require('docx');
  console.log("docx module loaded:", Object.keys(docx).join(", "));
} catch(e) {
  console.log("Error loading docx:", e.message);
}