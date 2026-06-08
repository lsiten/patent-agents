import { expect, test } from '@playwright/test';

const API_BASE_PATTERN = '**/api/v1';

test('workflow detail shows awaiting-user-decision remediation state and normalized score', async ({ page }) => {
  await page.route(`${API_BASE_PATTERN}/workflows/wf-remediation`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        task_id: 'wf-remediation',
        user_id: 'default_user',
        title: 'Low score remediation',
        current_state: 'awaiting_user_decision',
        created_at: '2026-06-08T00:00:00.000Z',
        updated_at: '2026-06-08T00:00:05.000Z',
        iteration_count: 2,
        message_count: 3,
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
          {
            phase: 'review',
            success: true,
            duration_seconds: 1,
            output: {
              review_summary: {
                overall_score: 0.78,
                overall_rating: 'needs_revision',
                recommendation: 'revise',
                reviewer_notes: '需要补充关键参数范围。',
              },
            },
            issues: [],
            warnings: [],
          },
        ],
        outputs: {
          brainstorming: {},
          requirement_analysis: {},
          retrieval_report: {},
          patent_draft: {},
          review_report: {
            review_summary: {
              overall_score: 0.78,
              overall_rating: 'needs_revision',
              recommendation: 'revise',
              reviewer_notes: '需要补充关键参数范围。',
            },
            recommendation: 'revise',
            formal_compliance: { issues: [] },
            claims_review: { issues: [] },
            description_review: { issues: [] },
          },
        },
        quality_remediation: {
          current_score: 0.78,
          threshold: 0.8,
          classification: 'needs_user_input',
          missing_information: ['核心实施例中的关键参数范围'],
          attempt_count: 2,
          recommended_next_action: 'provide_info',
          resume_phase: 'requirement_analysis',
        },
      }),
    });
  });

  await page.goto('/workflow/wf-remediation');

  await expect(page.getByTestId('quality-remediation-card')).toBeVisible();
  await expect(page.getByRole('heading', { name: '质量未达标，等待补充信息' })).toBeVisible();
  await expect(page.getByTestId('quality-remediation-card')).toBeVisible();
  await expect(page.getByText('核心实施例中的关键参数范围')).toBeVisible();
  await page.getByRole('tab', { name: '审查意见' }).click();
  await expect(page.getByText('78').first()).toBeVisible();
  await expect(page.getByText('流程失败')).toHaveCount(0);
});
