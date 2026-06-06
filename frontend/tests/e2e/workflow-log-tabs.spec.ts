import { expect, test, type Page } from '@playwright/test';

const API_BASE_PATTERN = '**/api/v1';

async function mockPatentWritingWorkflow(page: Page) {
  await page.route(`${API_BASE_PATTERN}/workflows/wf-writer`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        task_id: 'wf-writer',
        user_id: 'default_user',
        title: 'Writer log regression',
        current_state: 'patent_writing',
        created_at: '2026-06-04T00:00:00.000Z',
        updated_at: '2026-06-04T00:00:01.000Z',
        iteration_count: 0,
        message_count: 1,
        phase_history: [
          {
            phase: 'requirement_analysis',
            success: true,
            duration_seconds: 1,
            output: {},
            issues: [],
            warnings: [],
          },
          {
            phase: 'retrieval_analysis',
            success: true,
            duration_seconds: 1,
            output: {},
            issues: [],
            warnings: [],
          },
        ],
        outputs: {
          brainstorming: {},
          requirement_analysis: {},
          retrieval_report: {},
          patent_draft: {},
          review_report: {},
        },
      }),
    });
  });
}

async function mockWorkflowEventSource(page: Page) {
  await page.addInitScript(() => {
    class MockEventSource extends EventTarget {
      url: string;
      onerror: ((event: Event) => void) | null = null;

      constructor(url: string) {
        super();
        this.url = url;

        window.setTimeout(() => {
          const event = new MessageEvent('agent.dispatch', {
            data: JSON.stringify({
              task_id: 'wf-writer',
              timestamp: '2026-06-04T00:00:02.000Z',
              agent: 'CEO Agent',
              message: '调度 → 专利撰写 Agent',
              event_type: 'agent.dispatch',
              data: {
                from_agent: 'CEO Agent',
                to_agent: '专利撰写 Agent',
                task_description: '生成符合规范的专利申请文件',
              },
            }),
          });

          this.dispatchEvent(event);
        }, 50);
      }

      close() {}
    }

    window.EventSource = MockEventSource as typeof EventSource;
  });
}

test('workflow log filters include the agent targeted by a live dispatch event', async ({ page }) => {
  await mockPatentWritingWorkflow(page);
  await mockWorkflowEventSource(page);

  await page.goto('/workflow/wf-writer');

  await expect(page.getByText('专利撰写 Agent').first()).toBeVisible();
  await expect(page.getByRole('button', { name: /专利撰写 Agent/ })).toBeVisible();
});
