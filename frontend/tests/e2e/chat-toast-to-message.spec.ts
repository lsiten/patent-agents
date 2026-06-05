import { expect, test, type Page } from '@playwright/test';

const API_BASE_PATTERN = '**/api/v1';

async function mockConversationList(page: Page) {
  await page.route(`${API_BASE_PATTERN}/conversations?user_id=default_user`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total: 0, items: [] }),
    });
  });
}

async function mockCreateConversation(page: Page, id: string, title: string) {
  await page.route(`${API_BASE_PATTERN}/conversations`, async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id,
        title,
        created_at: '2026-06-04T00:00:00.000Z',
        updated_at: '2026-06-04T00:00:00.000Z',
        message_count: 0,
        status: 'draft',
        linked_workflow_id: null,
        messages: [],
      }),
    });
  });
}

test('invalid file type is shown as in-stream system message', async ({ page }) => {
  await mockConversationList(page);
  await page.goto('/chat');

  await page.getByTestId('chat-file-input').setInputFiles({
    name: 'invalid.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('invalid file'),
  });

  await expect(page.getByTestId('chat-system-message')).toContainText('文件类型不支持：仅支持 .txt 和 .docx 文件');
  await expect(page.getByText('文件类型不支持', { exact: true })).toHaveCount(0);
});

test('successful upload shows file message and auto-analysis system message', async ({ page }) => {
  await mockConversationList(page);
  await mockCreateConversation(page, 'conv-1', 'sample.txt');
  await page.route(`${API_BASE_PATTERN}/conversations/conv-1/upload`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        conversation_id: 'conv-1',
        filename: 'sample.txt',
        file_type: 'text/plain',
        file_size: 18,
        extracted_text: 'hello invention',
        message_id: 'file-msg-1',
        char_count: 18,
        metadata: {},
      }),
    });
  });
  await page.route(`${API_BASE_PATTERN}/conversations/conv-1/chat/stream`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'event: content',
        'data: {"content":"正在分析","has_recommendation":false}',
        '',
        'event: done',
        'data: {"message":{"id":"assistant-1","role":"assistant","content":"分析完成","timestamp":"2026-06-04T00:00:01.000Z"},"has_recommendation":false,"conversation_id":"conv-1"}',
        '',
      ].join('\n'),
    });
  });

  await page.goto('/chat');
  await page.getByTestId('chat-file-input').setInputFiles({
    name: 'sample.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('hello invention'),
  });
  await page.getByTestId('chat-send-button').click();

  await expect(page.getByTestId('chat-file-message')).toContainText('文件已解析：sample.txt · 18 字符');
  await expect(page.getByTestId('chat-system-message')).toContainText('正在分析文件：AI 正在解读您上传的交底书...');
  await expect(page.getByText('文件已解析', { exact: true })).toHaveCount(0);
  await expect(page.getByText('正在分析文件', { exact: true })).toHaveCount(0);
});

test('stream failure removes placeholder and appends system error message', async ({ page }) => {
  await mockConversationList(page);
  await mockCreateConversation(page, 'conv-2', '测试消息');
  await page.route(`${API_BASE_PATTERN}/conversations/conv-2/chat/stream`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'event: error',
        'data: {"error":"服务暂时不可用"}',
        '',
        '',
      ].join('\n'),
    });
  });

  await page.goto('/chat');
  await page.getByTestId('chat-input').click();
  await page.getByTestId('chat-input').pressSequentially('测试消息');
  await page.getByTestId('chat-send-button').click();

  await expect(page.getByTestId('chat-system-message')).toContainText('请求失败：服务暂时不可用');
  await expect(page.getByText('思考中')).toHaveCount(0);
  await expect(page.getByText('请求失败', { exact: true })).toHaveCount(0);
});

test('linked workflow conversation keeps chat box usable and streams workflow sync feedback', async ({ page }) => {
  await page.route(`${API_BASE_PATTERN}/conversations?user_id=default_user`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        total: 1,
        items: [{
          id: 'conv-linked',
          title: 'Linked workflow conversation',
          created_at: '2026-06-04T00:00:00.000Z',
          updated_at: '2026-06-04T00:00:00.000Z',
          message_count: 1,
          status: 'workflow_linked',
          linked_workflow_id: 'wf-linked',
        }],
      }),
    });
  });

  await page.route(`${API_BASE_PATTERN}/conversations/conv-linked`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'conv-linked',
        title: 'Linked workflow conversation',
        created_at: '2026-06-04T00:00:00.000Z',
        updated_at: '2026-06-04T00:00:00.000Z',
        message_count: 1,
        status: 'workflow_linked',
        linked_workflow_id: 'wf-linked',
        messages: [{
          id: 'assistant-welcome',
          role: 'assistant',
          content: '工作流已启动，可以继续补充技术细节。',
          timestamp: '2026-06-04T00:00:00.000Z',
          type: 'text',
          metadata: null,
        }],
      }),
    });
  });

  await page.route(`${API_BASE_PATTERN}/workflows/wf-linked`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        task_id: 'wf-linked',
        user_id: 'default_user',
        title: 'Linked workflow',
        current_state: 'patent_writing',
        created_at: '2026-06-04T00:00:00.000Z',
        updated_at: '2026-06-04T00:00:00.000Z',
        iteration_count: 0,
        message_count: 1,
        phase_history: [],
        outputs: {},
      }),
    });
  });

  await page.route(`${API_BASE_PATTERN}/conversations/conv-linked/chat/stream`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'event: content',
        'data: {"content":"补充信息已同步到关联工作流","has_recommendation":false}',
        '',
        'event: done',
        'data: {"message":{"id":"assistant-linked","role":"assistant","content":"补充信息已同步到关联工作流","timestamp":"2026-06-04T00:00:01.000Z"},"has_recommendation":false,"conversation_id":"conv-linked"}',
        '',
      ].join('\n'),
    });
  });

  await page.goto('/chat?conv_id=conv-linked');
  await expect(page.getByText('专利申请流程已启动')).toBeVisible();

  await page.getByTestId('chat-input').fill('补充：向外翻折时使用过渡画面补偿空白区域');
  await expect(page.getByTestId('chat-send-button')).toBeEnabled();
  await page.getByTestId('chat-send-button').click();

  await expect(page.getByText('补充信息已同步到关联工作流')).toBeVisible();
  await expect(page.getByText('该对话已关联工作流')).toHaveCount(0);
});
