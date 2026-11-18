// Converte o HTML do check diário em PDF A4 (Chromium do Playwright).
// Uso: NODE_PATH=$(npm root -g) node relatorios/html2pdf.js entrada.html saida.pdf
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [inp, out] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('file://' + path.resolve(inp));
  await p.pdf({ path: out, format: 'A4', printBackground: true, margin: { top: '8mm', bottom: '8mm', left: '0', right: '0' } });
  await b.close();
  console.log(out);
})();
