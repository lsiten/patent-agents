import { BookOpen, ChevronRight, GitBranch, Network, ShieldCheck } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Card, CardContent, CardDescription, CardTitle } from '@/components/ui/Card';
import type { WorkflowResponse } from '@/lib/api';

function valueToText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未记录';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value);
}

export function AgentLoopPanel({ workflow }: { workflow: WorkflowResponse | null }) {
  const loop = workflow?.agent_loop;
  const skills = workflow?.sedimented_skills ?? [];
  const topology = loop?.policy?.topology ?? [];
  const doneConditions = loop?.policy?.done_conditions ?? [];
  const guardrails = Object.entries(loop?.policy?.guardrails ?? {});
  const worktree = Object.entries(loop?.worktree ?? {});
  const feedback = loop?.feedback ?? {};
  const compliance = Object.entries(loop?.architecture_compliance ?? {});

  return (
    <Card className="min-w-0 overflow-hidden">
      <details>
        <summary className="flex cursor-pointer list-none items-center justify-between gap-md px-lg py-md transition-colors hover:bg-surface">
          <div className="min-w-0">
            <CardTitle>Agent Loop 与 Hermes 自进化</CardTitle>
            <CardDescription>
              通用 Loop 平台、领域工作流闭环和各 Agent 技能沉淀状态
            </CardDescription>
          </div>
          <ChevronRight className="h-5 w-5 flex-shrink-0 text-steel transition-transform details-open:rotate-90" />
        </summary>
        <CardContent className="min-w-0 space-y-lg overflow-hidden border-t border-line pt-lg">
          <div className="grid min-w-0 gap-md md:grid-cols-2 xl:grid-cols-4">
            <div className="min-w-0 rounded-lg border border-line bg-white p-md">
              <div className="mb-sm flex min-w-0 items-center gap-2 text-body-sm-medium text-ink">
                <Network className="h-4 w-4 flex-shrink-0 text-green" />
                <span className="truncate">Loop 拓扑</span>
              </div>
              <div className="flex min-w-0 flex-wrap gap-2">
                {(topology.length ? topology : ['等待快照']).map((item) => (
                  <Badge key={item} variant="green-soft" className="max-w-full truncate">
                    {item}
                  </Badge>
                ))}
              </div>
            </div>

            <div className="min-w-0 rounded-lg border border-line bg-white p-md">
              <div className="mb-sm flex min-w-0 items-center gap-2 text-body-sm-medium text-ink">
                <ShieldCheck className="h-4 w-4 flex-shrink-0 text-green" />
                <span className="truncate">Done 条件</span>
              </div>
              <ul className="min-w-0 space-y-1 text-caption text-steel">
                {(doneConditions.length ? doneConditions : ['等待快照生成']).slice(0, 4).map((item) => (
                  <li key={item} className="break-words">• {item}</li>
                ))}
              </ul>
            </div>

            <div className="min-w-0 rounded-lg border border-line bg-white p-md">
              <div className="mb-sm flex min-w-0 items-center gap-2 text-body-sm-medium text-ink">
                <GitBranch className="h-4 w-4 flex-shrink-0 text-green" />
                <span className="truncate">Guardrails</span>
              </div>
              <div className="min-w-0 space-y-1 text-caption text-steel">
                {(guardrails.length ? guardrails : [['status', '等待快照']]).slice(0, 5).map(([key, value]) => (
                  <div key={key} className="flex min-w-0 justify-between gap-2">
                    <span className="min-w-0 truncate">{key}</span>
                    <span className="max-w-[55%] truncate text-ink">{valueToText(value)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="min-w-0 rounded-lg border border-line bg-white p-md">
              <div className="mb-sm flex min-w-0 items-center gap-2 text-body-sm-medium text-ink">
                <BookOpen className="h-4 w-4 flex-shrink-0 text-green" />
                <span className="truncate">技能沉淀</span>
              </div>
              <p className="text-heading-5 font-euclid text-ink">{skills.length}</p>
              <p className="text-caption text-steel">个 Agent profile 已写入 Hermes SKILL.md</p>
            </div>
          </div>

          <div className="grid min-w-0 gap-md lg:grid-cols-2">
            <div className="min-w-0 rounded-lg border border-line bg-white p-md">
              <h3 className="mb-sm text-body-sm-medium text-ink">反馈闭环</h3>
              <div className="grid min-w-0 gap-sm sm:grid-cols-2">
                <div className="min-w-0">
                  <p className="text-caption text-steel">审查建议</p>
                  <p className="break-words text-body-sm text-ink">{valueToText(feedback.review_recommendation)}</p>
                </div>
                <div className="min-w-0">
                  <p className="text-caption text-steel">审查分</p>
                  <p className="break-words text-body-sm text-ink">{valueToText(feedback.review_score)}</p>
                </div>
              </div>
            </div>

            <div className="min-w-0 rounded-lg border border-line bg-white p-md">
              <h3 className="mb-sm text-body-sm-medium text-ink">工作树</h3>
              <div className="min-w-0 space-y-1 text-caption text-steel">
                {(worktree.length ? worktree : [['path', '等待快照']]).slice(0, 5).map(([key, value]) => (
                  <div key={key} className="grid min-w-0 grid-cols-[7rem_minmax(0,1fr)] gap-2">
                    <span className="truncate">{key}</span>
                    <span className="min-w-0 truncate text-ink" title={valueToText(value)}>{valueToText(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="min-w-0 rounded-lg border border-line bg-white p-md">
            <h3 className="mb-sm text-body-sm-medium text-ink">架构符合度</h3>
            {compliance.length === 0 ? (
              <p className="text-body-sm text-steel">等待 Agent Loop 快照生成。</p>
            ) : (
              <div className="grid min-w-0 gap-sm md:grid-cols-2">
                {compliance.map(([key, raw]) => {
                  const item = raw && typeof raw === 'object' && !Array.isArray(raw)
                    ? raw as Record<string, unknown>
                    : {};
                  const label = typeof item.label === 'string' ? item.label : key;
                  const score = typeof item.score === 'number' ? item.score : 0;
                  const evidence = Array.isArray(item.evidence)
                    ? item.evidence.filter((entry): entry is string => typeof entry === 'string')
                    : [];
                  return (
                    <div key={key} className="min-w-0 rounded-md border border-line/70 p-sm">
                      <div className="flex min-w-0 items-center justify-between gap-2">
                        <span className="min-w-0 truncate text-body-sm-medium text-ink">{label}</span>
                        <Badge variant={score >= 100 ? 'green-soft' : 'orange'}>{score}%</Badge>
                      </div>
                      {evidence[0] && (
                        <p className="mt-1 truncate text-caption text-steel" title={evidence.join('；')}>
                          {evidence[0]}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="min-w-0 rounded-lg border border-line bg-white p-md">
            <h3 className="mb-sm text-body-sm-medium text-ink">各 Agent 自有技能</h3>
            {skills.length === 0 ? (
              <p className="text-body-sm text-steel">流程终态后会按 Agent 写入 profile-local Hermes 技能。</p>
            ) : (
              <div className="grid min-w-0 gap-sm md:grid-cols-2">
                {skills.map((skill) => (
                  <div key={`${skill.agent_profile}-${skill.skill}`} className="min-w-0 rounded-md border border-line/70 p-sm">
                    <div className="flex min-w-0 items-center justify-between gap-2">
                      <span className="min-w-0 truncate text-body-sm-medium text-ink">{skill.agent_profile}</span>
                      <Badge variant="green-soft" className="max-w-[60%] truncate">{skill.skill}</Badge>
                    </div>
                    <p className="mt-1 truncate text-caption text-steel" title={skill.skill_path}>
                      {skill.skill_path || 'SKILL.md'}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </details>
    </Card>
  );
}
