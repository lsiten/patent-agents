const { chromium } = await import('./frontend/node_modules/playwright/index.mjs');

const filePath = '/Users/leishicheng/Documents/workspace/code/patent-agents-clean/20260506075628-45-基于Cave折幕视频的处理方法及系统-茅-逐字稿文本-1.txt';
const prompt = `请基于上传的交底沟通逐字稿生成完整发明专利申请文件。
要求：先从沟通内容中分析专利主题、方向和技术细节；进入正式撰写前必须确认需求分析问题和检索问题已解决；按完整流程执行需求分析、真实检索、分段撰写、附图生成和质量审查。
如果质量审查不合格，不要结束流程，由 CEO 调度对应 Agent 基于上一轮内容和反馈继续补充优化，直到审查合格后再生成最终 DOCX。
权利要求书必须由独权和从权组成；独权只能以3步或4步组成；每个分号和句号后必须换行。`;

const browser = await chromium.launch({ headless: false, slowMo: 80 });
const page = await browser.newPage({ viewport: { width: 1440, height: 980 } });
await page.goto('http://localhost:3000/chat', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1200);

const newChat = page.getByRole('button', { name: /新建对话/ }).first();
if (await newChat.count()) {
  await newChat.click();
  await page.waitForTimeout(800);
}

const fileInput = page.locator('input[type="file"]').first();
await fileInput.setInputFiles(filePath);
await page.waitForTimeout(1000);

const textbox = page.locator('textarea, [contenteditable="true"], input[type="text"]').last();
await textbox.click();
await textbox.fill(prompt);
await page.waitForTimeout(300);

const sendButton = page.locator('button').filter({ has: page.locator('svg') }).last();
if (await sendButton.count()) {
  await sendButton.click();
} else {
  await textbox.press('Enter');
}

await page.waitForTimeout(5000);
const url = page.url();
const text = await page.locator('body').innerText({ timeout: 5000 });
console.log(JSON.stringify({ url, bodyPreview: text.slice(0, 2000) }, null, 2));
await page.screenshot({ path: '/Users/leishicheng/Documents/workspace/code/patent-agents-clean/.browser-real-generation-started.png', fullPage: false });

// Keep the browser open for observation while the workflow runs.
await new Promise(() => {});
