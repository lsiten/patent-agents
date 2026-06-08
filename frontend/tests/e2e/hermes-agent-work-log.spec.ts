import { expect, test } from '@playwright/test';

test('chat shows which Hermes agent is working and what it is doing', async ({ page }) => {
  const errors: string[] = [];
  const requests: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/')) requests.push(request.url());
  });
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  const convId = 'conv-agent-work';
  const taskId = 'workflow-agent-work';
  const now = new Date().toISOString();
  let includeProgressMessage = false;

  await page.route('**/api/v1/conversations?user_id=default_user', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        total: 1,
        items: [
          {
            id: convId,
            user_id: 'default_user',
            title: '智能专利撰写系统',
            created_at: now,
            updated_at: now,
            message_count: 2,
            status: 'workflow_linked',
            workflow_task_id: taskId,
            linked_workflow_id: taskId,
            workflow_state: 'brainstorming',
          },
        ],
      }),
    });
  });

  await page.route(`**/api/v1/conversations/${convId}`, async (route) => {
    const messages = [
      {
        id: 'assistant-greeting',
        role: 'assistant',
        content: '专利申请流程已启动。',
        timestamp: now,
        type: 'text',
        metadata: null,
      },
    ];
    if (includeProgressMessage) {
      messages.push({
        id: 'agent-progress-1',
        role: 'agent',
        agent_name: '需求分析师',
        content: '需求分析师：分析技术方案并提取创新点',
        timestamp: now,
        type: 'progress',
        metadata: {
          workflow_id: taskId,
          event_type: 'agent.work.started',
          agent_id: 'requirement_analyst',
          status: 'running',
          task: '分析技术方案并提取创新点',
        },
      } as never);
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        id: convId,
        user_id: 'default_user',
        title: '智能专利撰写系统',
        created_at: now,
        updated_at: now,
        message_count: messages.length,
        status: 'workflow_linked',
        workflow_task_id: taskId,
        linked_workflow_id: taskId,
        workflow_state: 'brainstorming',
        messages,
      }),
    });
  });


  await page.route(`**/api/v1/workflows/${taskId}`, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        task_id: taskId,
        user_id: 'default_user',
        current_state: 'brainstorming',
        created_at: now,
        updated_at: now,
        iteration_count: 0,
        progress: 10,
        phase_history: [],
      }),
    });
  });

  await page.addInitScript(({ convId, taskId, now }) => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof Request ? input.url : input.toString();
      if (!url.includes(`/api/v1/conversations/${convId}/events/stream`)) {
        return originalFetch(input, init);
      }

      const event = {
        event_type: 'agent.work.started',
        task_id: taskId,
        conversation_id: convId,
        agent_id: 'requirement_analyst',
        agent_name: '需求分析师',
        action: '分析技术方案并提取创新点',
        status: 'running',
        timestamp: now,
        data: { task: '分析技术方案并提取创新点' },
      };
      const message = {
        id: 'agent-progress-1',
        role: 'agent',
        agent_name: '需求分析师',
        content: '需求分析师：分析技术方案并提取创新点',
        timestamp: now,
        type: 'progress',
        metadata: {
          workflow_id: taskId,
          event_type: 'agent.work.started',
          agent_id: 'requirement_analyst',
          status: 'running',
          task: '分析技术方案并提取创新点',
        },
      };
      const body = [
        `event: agent_work\ndata: ${JSON.stringify(event)}\n\n`,
        `event: conversation_message\ndata: ${JSON.stringify(message)}\n\n`,
      ].join('');
      const chunks = [body.slice(0, 12), body.slice(12, 64), body.slice(64)];
      const stream = new ReadableStream({
        start(controller) {
          const encoder = new TextEncoder();
          for (const chunk of chunks) {
            controller.enqueue(encoder.encode(chunk));
          }
          controller.close();
        },
      });

      return Promise.resolve(new Response(stream, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }));
    };
  }, { convId, taskId, now });

  await page.goto(`/chat?conv_id=${convId}`);

  await page.getByText('需求分析师').first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => undefined);
  if (!(await page.getByText('需求分析师').first().isVisible().catch(() => false))) {
    throw new Error(`需求分析师 not visible. Browser errors: ${errors.join(' | ')}. Requests: ${requests.join(' | ')}`);
  }
  await expect(page.getByText('分析技术方案并提取创新点').first()).toBeVisible();
  await expect(page.getByText('CEO 调度')).toBeVisible();
});

test('chat activity log shows specialist agent name for agent events', async ({ page }) => {
  const convId = 'conv-agent-activity-name';
  const now = new Date().toISOString();

  await page.route('**/api/v1/conversations?user_id=default_user', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        total: 1,
        items: [
          {
            id: convId,
            user_id: 'default_user',
            title: '智能专利撰写系统',
            created_at: now,
            updated_at: now,
            message_count: 1,
            status: 'active',
            linked_workflow_id: null,
          },
        ],
      }),
    });
  });

  await page.route(`**/api/v1/conversations/${convId}`, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        id: convId,
        user_id: 'default_user',
        title: '智能专利撰写系统',
        created_at: now,
        updated_at: now,
        message_count: 1,
        status: 'active',
        linked_workflow_id: null,
        messages: [
          {
            id: 'assistant-with-agent-events',
            role: 'assistant',
            content: '分析过程如下。',
            timestamp: now,
            type: 'text',
            metadata: null,
            agent_events: [
              {
                id: 'evt-specialist-thinking',
                sequence: 1,
                call_id: 'call-specialist',
                type: 'thinking',
                agent_name: '需求分析师',
                timestamp: now,
                message: '正在拆解技术方案',
                data: {},
              },
            ],
          },
        ],
      }),
    });
  });

  await page.goto(`/chat?conv_id=${convId}`);

  await expect(page.getByText('Agent 活动日志')).toBeVisible();
  await expect(page.getByText('正在拆解技术方案')).toBeVisible();
  await expect(page.getByText('需求分析师')).toBeVisible();
});

test('chat activity log maps raw Hermes profile ids to display names', async ({ page }) => {
  const convId = 'conv-agent-profile-id-name';
  const now = new Date().toISOString();

  await page.route('**/api/v1/conversations?user_id=default_user', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        total: 1,
        items: [
          {
            id: convId,
            user_id: 'default_user',
            title: '智能专利撰写系统',
            created_at: now,
            updated_at: now,
            message_count: 1,
            status: 'active',
            linked_workflow_id: null,
          },
        ],
      }),
    });
  });

  await page.route(`**/api/v1/conversations/${convId}`, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        id: convId,
        user_id: 'default_user',
        title: '智能专利撰写系统',
        created_at: now,
        updated_at: now,
        message_count: 1,
        status: 'active',
        linked_workflow_id: null,
        messages: [
          {
            id: 'assistant-with-ceo-profile-event',
            role: 'assistant',
            content: '分析过程如下。',
            timestamp: now,
            type: 'text',
            metadata: null,
            agent_events: [
              {
                id: 'evt-ceo-thinking',
                sequence: 1,
                call_id: 'call-ceo',
                type: 'thinking',
                agent_name: 'patent.ceo.v1',
                timestamp: now,
                message: 'reflecting...',
                data: {},
              },
            ],
          },
        ],
      }),
    });
  });

  await page.goto(`/chat?conv_id=${convId}`);

  await expect(page.getByText('Agent 活动日志')).toBeVisible();
  await expect(page.getByText('reflecting...')).toBeVisible();
  await expect(page.getByText('CEO Agent')).toBeVisible();
  await expect(page.getByText('patent.ceo.v1')).toHaveCount(0);
});
