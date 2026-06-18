const { chromium } = require("../frontend/node_modules/playwright");
const fs = require("fs");

const transcriptPath =
  "/Users/leishicheng/Documents/workspace/code/patent-agents-clean/20260506075628-45-基于Cave折幕视频的处理方法及系统-茅-逐字稿文本-1.txt";

const firstPrompt = `请基于上传的逐字稿交底内容，先进行头脑风暴和交底清洗：提炼真实专利主题、专利名称、技术问题、核心方案、关键创新点、待补充问题和附图计划。不要直接启动专利申请流程；只有在专利名称、专利类型、公开状态、独立权利要求主线和完整技术方案都确认后，再由我点击/确认启动正式流程。正式流程需按需求分析、现有技术检索、专利撰写、附图生成、质量审查生成最终DOCX，且必须符合《专利申请文件撰写完整规范手册.md》：独立权利要求只能由3步或4步组成，权利要求中每个分号和句号后必须换行。`;

const confirmPrompt = `确认启动前信息，但请先展示启动确认条并等待我点击：
专利名称：一种沉浸式折幕空间的屏幕姿态联动显示处理方法及系统。
专利类型：发明专利。
公开状态：尚未公开。
独立权利要求主线：采用4步，步骤1获取空间配置、显示单元配置、用户信息和/或场景信息；步骤2基于预设映射关系确定目标屏幕姿态、显示状态和画面处理策略；步骤3控制至少一个显示单元执行姿态调整，并联动输出待显示画面；步骤4根据外转、内转、遮挡、重叠或空白区域执行补充、裁切、删除、重构或重映射处理。
技术方案确认：转动机构、角度范围、传感器和显示设备形式不写死，写成可选执行机构、角度区间、传感/反馈方式和投影/LED/屏幕等显示单元；映射关系由用户身高、入口交互、视频内容、场景模式和显示单元当前姿态中的至少一种确定。
附图计划确认：整体系统结构图、显示单元外转补充示意图、显示单元内转裁切/重构示意图、方法流程图、交互与身高映射示意图、映射关系/画面处理逻辑图。`;

async function visibleEditable(page) {
  const loc = page.locator('textarea:enabled, [contenteditable="true"]').filter({ hasNotText: "" });
  const count = await loc.count();
  for (let i = count - 1; i >= 0; i -= 1) {
    const item = loc.nth(i);
    if (await item.isVisible().catch(() => false)) return item;
  }
  return page.locator("textarea:enabled").last();
}

async function sendMessage(page, text) {
  await page.locator("textarea:enabled, [contenteditable='true']").first().waitFor({ state: "visible", timeout: 120000 });
  const input = await visibleEditable(page);
  await input.click();
  const tag = await input.evaluate((el) => el.tagName.toLowerCase());
  if (tag === "textarea") {
    await input.fill(text);
  } else {
    await input.evaluate((el, value) => {
      el.textContent = value;
      el.dispatchEvent(new InputEvent("input", { bubbles: true, data: value }));
    }, text);
  }
  await page.waitForTimeout(300);
  const sendButtons = page.locator('button:visible').filter({ hasText: /^$/ });
  const explicit = page.locator('[data-testid="send-button"], button[aria-label*="发送"], button[title*="发送"]');
  if (await explicit.count()) {
    await explicit.last().click();
  } else if (await sendButtons.count()) {
    await sendButtons.last().click();
  } else {
    await input.press("Enter");
  }
}

async function waitForAssistantTurn(page, previousCount, timeout = 240000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const count = await page.locator('[data-testid="chat-message-assistant"]').count().catch(() => 0);
    const inputEnabled = await page.locator("textarea:enabled").count().catch(() => 0);
    if (count > previousCount && inputEnabled > 0) {
      return await page.locator("body").innerText().catch(() => "");
    }
    await page.waitForTimeout(1500);
  }
  throw new Error("Timed out waiting for assistant turn");
}

async function waitForAnyText(page, patterns, timeout = 180000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const body = await page.locator("body").innerText().catch(() => "");
    for (const pattern of patterns) {
      if (pattern.test(body)) return body;
    }
    await page.waitForTimeout(1500);
  }
  throw new Error(`Timed out waiting for ${patterns.map(String).join(", ")}`);
}

(async () => {
  if (!fs.existsSync(transcriptPath)) {
    throw new Error(`Transcript not found: ${transcriptPath}`);
  }
  const browser = await chromium.launch({
    headless: false,
    args: ["--window-size=1600,1000"],
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  page.setDefaultTimeout(30000);
  await page.goto("http://localhost:3000/chat", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle").catch(() => {});

  const newChat = page.getByRole("button", { name: /新建对话/ });
  if (await newChat.count()) await newChat.first().click();
  await page.waitForTimeout(800);

  const fileInput = page.locator('input[type="file"]').first();
  if ((await fileInput.count()) === 0) throw new Error("No file input found");
  await fileInput.setInputFiles(transcriptPath);
  await page.waitForTimeout(800);

  const assistantCountBefore = await page.locator('[data-testid="chat-message-assistant"]').count().catch(() => 0);
  await sendMessage(page, firstPrompt);
  const brainstormText = await waitForAssistantTurn(page, assistantCountBefore, 300000);
  console.log("BRAINSTORM_READY");
  console.log(brainstormText.slice(-3000));

  const directionButtons = page.getByRole("button", { name: /是，按该主线继续清洗/ });
  if (await directionButtons.count()) {
    const beforeDirection = await page.locator('[data-testid="chat-message-assistant"]').count().catch(() => 0);
    await directionButtons.first().click();
    await waitForAssistantTurn(page, beforeDirection, 300000).catch(() => {});
  }

  const assistantCountBeforeConfirm = await page.locator('[data-testid="chat-message-assistant"]').count().catch(() => 0);
  await sendMessage(page, confirmPrompt);
  await waitForAssistantTurn(page, assistantCountBeforeConfirm, 300000);
  await waitForAnyText(page, [/启动专利申请/, /专利名称：/, /技术方案已基本清晰/], 60000);

  const startButtons = page.getByRole("button", { name: /启动专利申请/ });
  const startCount = await startButtons.count();
  if (!startCount) throw new Error("Start workflow button not found");
  await startButtons.nth(startCount - 1).click();
  await page.waitForTimeout(1500);

  const started = await waitForAnyText(page, [/任务编号[:：]\s*[0-9a-f-]{36}/, /专利申请流程已创建/], 60000);
  const match = started.match(/任务编号[:：]\s*([0-9a-f-]{36})/);
  console.log(`TASK_ID=${match ? match[1] : "UNKNOWN"}`);
  console.log(`URL=${page.url()}`);
  await page.screenshot({ path: "/Users/leishicheng/Documents/workspace/code/patent-agents-clean/.codex-tmp/latest-browser-start.png", fullPage: false });
  await browser.close();
})().catch(async (error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
