const { chromium } = require('../frontend/node_modules/playwright');

const disclosurePath =
  '/Users/leishicheng/Documents/workspace/code/patent-agents-clean/20260506075628-45-基于Cave折幕视频的处理方法及系统-茅-逐字稿文本-1.txt';

async function clickIfVisible(page, pattern, label, timeout = 1500) {
  const candidates = [
    page.getByRole('button', { name: pattern }).first(),
    page.getByText(pattern).first(),
  ];
  for (const candidate of candidates) {
    try {
      await candidate.waitFor({ state: 'visible', timeout });
      await candidate.click();
      console.log('CLICKED', label);
      return true;
    } catch (_) {
      // Try the next locator shape. Some chat action chips are text-first, not button-first.
    }
  }
  return false;
}

async function clickCurrentRecommendedChoice(page, timeout = 1500) {
  if (!page.url().includes('/chat') || !page.url().includes('conv_id=')) {
    return false;
  }
  const option = page.getByTestId('pending-confirmation-option').first();
  try {
    await option.waitFor({ state: 'visible', timeout });
    const text = (await option.innerText()).replace(/\s+/g, ' ').trim();
    await option.click({ timeout });
    console.log('CLICKED_RECOMMENDED_CHOICE', text.slice(0, 80));
    return true;
  } catch (_) {
    return false;
  }
}

async function main() {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 980 },
    acceptDownloads: true,
  });
  const page = await context.newPage();
  page.on('console', (message) => console.log('[console]', message.type(), message.text()));
  page.on('pageerror', (error) => console.log('[pageerror]', error.message));
  page.on('requestfailed', (request) => {
    console.log('[requestfailed]', request.method(), request.url(), request.failure()?.errorText || '');
  });

  await page.goto(process.env.RESUME_URL || 'http://localhost:3000/chat', {
    waitUntil: 'networkidle',
    timeout: 60000,
  });
  console.log('OPENED', page.url());
  if (!process.env.RESUME_URL) {
    await page.getByRole('button', { name: /新建对话/ }).first().click();
    await page.locator('input[type=file]').setInputFiles(disclosurePath);
    const input = page.locator('textarea[data-testid="chat-input"], textarea').last();
    await input.fill(
      '请基于上传的逐字稿文本，先头脑风暴并给出专利名称，确认后再启动完整专利申请流程；最终生成符合专利申请文件撰写完整规范手册的DOCX。'
    );
    await page.getByTestId('chat-send-button').click();
    console.log('SENT_DISCLOSURE');
  }

  const startedAt = Date.now();
  let clickedStart = false;
  while (Date.now() - startedAt < 240000) {
    await page.waitForTimeout(2500);
    const text = await page.locator('body').innerText().catch(() => '');
    if (text.includes('专利名称') || text.includes('发明名称')) {
      console.log('TITLE_OR_BRAINSTORM_VISIBLE');
    }
    await clickCurrentRecommendedChoice(page);
    if (await clickIfVisible(page, /启动专利申请/, 'start-workflow')) {
      clickedStart = true;
      break;
    }
    await clickIfVisible(page, /继续自动修复/, 'auto-repair');
    console.log(
      'TICK',
      Math.round((Date.now() - startedAt) / 1000),
      page.url(),
      text.slice(-500).replace(/\s+/g, ' ')
    );
  }

  console.log('CLICKED_START_WORKFLOW', clickedStart);
  console.log('URL', page.url());
  console.log('BODY_TAIL\n' + (await page.locator('body').innerText()).slice(-3000));

  await page.waitForTimeout(10 * 60 * 1000);
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
