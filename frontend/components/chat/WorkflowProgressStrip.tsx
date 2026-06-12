'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Brain,
  Search,
  FileText,
  CheckCircle2,
  XCircle,
  Loader2,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Play,
  Lightbulb,
} from 'lucide-react';
import { clsx } from 'clsx';
import { workflowApi } from '@/lib/api';
import type { WorkflowPhaseResult } from '@/lib/api';
import type { DispatchActivity } from './DispatchPanel';

interface WorkflowProgressStripProps {
  taskId?: string | null;
  currentState: string | null;
  refreshKey?: number;
  dispatchActivities?: DispatchActivity[];
  isStreaming?: boolean;
}

const STAGES: Array<{
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  matchStates: string[];
}> = [
  {
    id: 'brainstorm',
    label: '头脑风暴',
    icon: Lightbulb,
    matchStates: ['brainstorm', 'brainstorming'],
  },
  {
    id: 'requirement',
    label: '需求分析',
    icon: Brain,
    matchStates: ['requirement', 'requirement_analysis'],
  },
  {
    id: 'retrieval',
    label: '检索分析',
    icon: Search,
    matchStates: ['retrieval', 'retrieval_analysis'],
  },
  {
    id: 'writing',
    label: '专利撰写',
    icon: FileText,
    matchStates: ['writing', 'patent_writing'],
  },
  {
    id: 'review',
    label: '质量审查',
    icon: CheckCircle2,
    matchStates: ['review', 'reviewing', 'quality_review', 'iteration', 'awaiting_user_decision'],
  },
];

const AGENT_DISPLAY: Record<string, { name: string; emoji: string }> = {
  brainstorm_partner: { name: '头脑风暴', emoji: '💡' },
  requirement_analyst: { name: '需求分析', emoji: '🧠' },
  retrieval_analyst: { name: '检索分析', emoji: '🔍' },
  patent_writer: { name: '专利撰写', emoji: '✍️' },
  quality_reviewer: { name: '质量审查', emoji: '✅' },
};

function getAgentInfo(agentId: string) {
  return AGENT_DISPLAY[agentId] || { name: agentId, emoji: '🤖' };
}

function resolveStageIndex(
  currentState: string | null,
  phaseHistory: WorkflowPhaseResult[],
): { activeIndex: number; completedSet: Set<string> } {
  const completedSet = new Set<string>();
  for (const phase of phaseHistory) {
    if (phase.success) {
      completedSet.add(phase.phase);
    }
  }

  // 找到最后一个完成的阶段索引
  let lastCompletedIndex = -1;
  for (let i = STAGES.length - 1; i >= 0; i--) {
    const stage = STAGES[i];
    if (stage.matchStates.some((m) => completedSet.has(m))) {
      lastCompletedIndex = i;
      break;
    }
  }

  // 如果有完成的阶段，那么该阶段之前的所有阶段都应该被视为已完成（顺序执行）
  if (lastCompletedIndex >= 0) {
    for (let i = 0; i <= lastCompletedIndex; i++) {
      const stage = STAGES[i];
      for (const state of stage.matchStates) {
        completedSet.add(state);
      }
    }
  }

  let activeIndex = STAGES.findIndex((s) =>
    s.matchStates.includes(currentState ?? '')
  );
  if (activeIndex === -1) {
    if (currentState === 'completed') {
      activeIndex = STAGES.length;
    } else if (currentState === 'failed' || currentState === 'cancelled') {
      activeIndex = lastCompletedIndex !== -1 ? lastCompletedIndex + 1 : 0;
    } else {
      activeIndex = 0;
    }
  }
  return { activeIndex, completedSet };
}

export function WorkflowProgressStrip({
  taskId,
  currentState,
  refreshKey,
  dispatchActivities = [],
  isStreaming = false,
}: WorkflowProgressStripProps) {
  const router = useRouter();
  const [phaseHistory, setPhaseHistory] = useState<WorkflowPhaseResult[]>([]);
  const [latestState, setLatestState] = useState<string | null>(currentState);
  const [dispatchExpanded, setDispatchExpanded] = useState(true);
  const [dispatchItemExpanded, setDispatchItemExpanded] = useState<string | null>(null);
  const [phaseActivities, setPhaseActivities] = useState<DispatchActivity[]>([]);

  const PHASE_TO_AGENT: Record<string, string> = {
    brainstorm: 'brainstorm_partner',
    requirement: 'requirement_analyst',
    retrieval: 'retrieval_analyst',
    writing: 'patent_writer',
    review: 'quality_reviewer',
  };
  const STATE_TO_AGENT: Record<string, string> = {
    brainstorming: 'brainstorm_partner',
    requirement_analysis: 'requirement_analyst',
    retrieval_analysis: 'retrieval_analyst',
    patent_writing: 'patent_writer',
    quality_review: 'quality_reviewer',
    awaiting_user_decision: 'quality_reviewer',
  };

  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;

    const fetchWorkflow = async () => {
      try {
        const workflow = await workflowApi.get(taskId);
        if (cancelled) return;
        setPhaseHistory(workflow.phase_history || []);
        setLatestState(workflow.current_state);

        const history = workflow.phase_history || [];
        const activities: DispatchActivity[] = history.map((phase, i) => {
          const agentId = PHASE_TO_AGENT[phase.phase] || phase.phase;
          return {
            id: `phase-${phase.phase}-${i}`,
            agentId,
            agentName: agentId,
            task: phase.phase === 'brainstorm' ? '技术方案头脑风暴讨论'
              : phase.phase === 'requirement' ? '专利需求分析与创新点提取'
              : phase.phase === 'retrieval' ? '现有技术多源检索与对比'
              : phase.phase === 'writing' ? '专利文件撰写与术语规范'
              : phase.phase === 'review' ? '形式与实质双重质量审查'
              : phase.phase,
            status: phase.success ? 'completed' : 'failed',
            startedAt: '',
            completedAt: new Date().toISOString(),
            result: phase.issues?.length ? phase.issues.join('; ') : undefined,
          };
        });
        const currentAgentId = STATE_TO_AGENT[workflow.current_state];
        if (currentAgentId && !activities.some(a => a.agentId === currentAgentId)) {
          activities.push({
            id: `phase-${workflow.current_state}-active`,
            agentId: currentAgentId,
            agentName: currentAgentId,
            task: workflow.current_state === 'brainstorming' ? '技术方案头脑风暴讨论'
              : workflow.current_state === 'requirement_analysis' ? '专利需求分析与创新点提取'
              : workflow.current_state === 'retrieval_analysis' ? '现有技术多源检索与对比'
              : workflow.current_state === 'patent_writing' ? '专利文件撰写与术语规范'
              : workflow.current_state === 'quality_review' ? '形式与实质双重质量审查'
              : workflow.current_state,
            status: 'running',
            startedAt: new Date().toISOString(),
          });
        }
        setPhaseActivities(activities);

        // Stop polling once workflow reaches a terminal state
        const terminalStates = ['completed', 'failed', 'cancelled'];
        if (terminalStates.includes(workflow.current_state)) {
          cancelled = true;
          clearInterval(interval);
        }
      } catch {
      }
    };

    void fetchWorkflow();
    const interval = setInterval(fetchWorkflow, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [taskId, refreshKey]);

  const [starting, setStarting] = useState(false);

  // Merge phase_history activities + CEO dispatch activities, deduplicating by agentId.
  // Prefer dispatch activities (richer data) when both exist for the same agent.
  const dispatchAgentIds = new Set(dispatchActivities.map((a) => a.agentId));
  const uniquePhaseActivities = phaseActivities.filter((a) => !dispatchAgentIds.has(a.agentId));
  const allActivities = [...uniquePhaseActivities, ...dispatchActivities];

  const showDispatch = allActivities.length > 0 || isStreaming || !!taskId;

  // Hide the panel entirely if nothing to show
  if (!taskId && !showDispatch) return null;

  const { activeIndex, completedSet } = resolveStageIndex(latestState, phaseHistory);
  const isInitial = latestState === 'initial' || latestState === 'created';
  const isAwaitingDecision = latestState === 'awaiting_user_decision';
  const isTerminal = latestState === 'completed' || latestState === 'failed' || latestState === 'cancelled';

  const handleStart = async () => {
    if (!taskId || starting) return;
    setStarting(true);
    try {
      await workflowApi.start(taskId);
      setLatestState('requirement_analysis');
    } catch {
      // ignore — polling will pick up real state
    } finally {
      setStarting(false);
    }
  };

  const runningCount = allActivities.filter((a) => a.status === 'running').length;
  const completedCount = allActivities.filter((a) => a.status === 'completed').length;
  const failedCount = allActivities.filter((a) => a.status === 'failed').length;

  return (
    <div className="max-w-full min-w-0 overflow-hidden border-b border-hairline bg-canvas/60">
      {/* Unified CEO Dispatch Panel (stage roadmap + dispatch activities merged) */}
      {showDispatch && (
        <div className="min-w-0 px-4 py-2 md:px-6">
          <div className="w-full min-w-0">
            {/* Header: CEO 调度 title + workflow status + counters + collapse button */}
            <div className="flex min-w-0 items-center justify-between gap-3">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="text-xs font-medium text-slate">CEO 调度</span>
                {taskId && isInitial && !starting && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-amber-600">
                    <Loader2 className="w-3 h-3" />
                    等待开始
                  </span>
                )}
                {taskId && starting && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-blue-600">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    启动中…
                  </span>
                )}
                {taskId && latestState === 'completed' && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-green-600">
                    <CheckCircle2 className="w-3 h-3" />
                    已完成
                  </span>
                )}
                {taskId && latestState === 'failed' && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-red-600">
                    <XCircle className="w-3 h-3" />
                    流程失败
                  </span>
                )}
                {taskId && latestState === 'cancelled' && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-orange-600">
                    <XCircle className="w-3 h-3" />
                    已取消
                  </span>
                )}
                {taskId && isAwaitingDecision && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-purple-600">
                    <Lightbulb className="w-3 h-3" />
                    安全暂停
                  </span>
                )}
                {!isTerminal && !isInitial && !starting && (
                  <>
                    {allActivities.length === 0 && isStreaming && (
                      <span className="inline-flex items-center gap-1 text-[11px] text-blue-600">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        分析中
                      </span>
                    )}
                    {runningCount > 0 && (
                      <span className="inline-flex items-center gap-1 text-[11px] text-blue-600">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        {runningCount} 进行中
                      </span>
                    )}
                  </>
                )}
                {completedCount > 0 && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-green-600">
                    <CheckCircle2 className="w-3 h-3" />
                    {completedCount} 已完成
                  </span>
                )}
                {failedCount > 0 && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-red-600">
                    <XCircle className="w-3 h-3" />
                    {failedCount} 失败
                  </span>
                )}
              </div>
              <div className="flex flex-shrink-0 items-center gap-2">
                {taskId && isInitial && (
                  <button
                    onClick={handleStart}
                    disabled={starting}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium
                      text-white bg-brand-green hover:bg-brand-green-dark rounded-md
                      disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {starting ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Play className="w-3 h-3" />
                    )}
                    开始流程
                  </button>
                )}
                {taskId && (
                  <button
                    onClick={() => router.push(`/workflow/${encodeURIComponent(taskId)}`)}
                    className="inline-flex items-center gap-1 text-[11px] text-brand-green-dark hover:underline"
                  >
                    <ExternalLink className="w-3 h-3" />
                    详情
                  </button>
                )}
                <button
                  onClick={() => setDispatchExpanded(!dispatchExpanded)}
                  className="p-0.5 rounded hover:bg-canvas transition-colors"
                  title={dispatchExpanded ? '收起' : '展开'}
                >
                  {dispatchExpanded ? (
                    <ChevronUp className="w-3.5 h-3.5 text-slate" />
                  ) : (
                    <ChevronDown className="w-3.5 h-3.5 text-slate" />
                  )}
                </button>
              </div>
            </div>

            {/* Stage roadmap — below the CEO header when a workflow is active */}
            {taskId && (
              <div className="mt-3 border-t border-hairline/60 pt-3">
                <div className="flex min-w-0 flex-wrap gap-2">
                {STAGES.map((stage, idx) => {
                  // 检查该阶段是否完成
                  const isCompleted = stage.matchStates.some((m) => completedSet.has(m));
                  const isActive = idx === activeIndex && !isTerminal && !isInitial;
                  const Icon = stage.icon;

                  return (
                    <div key={stage.id} className="min-w-0 max-w-full flex-none">
                      <div
                        className={clsx(
                          'flex min-w-0 items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors',
                          isCompleted && 'bg-green-50 text-green-700',
                          isActive && 'bg-blue-50 text-blue-700 ring-1 ring-blue-200',
                          !isCompleted && !isActive && 'bg-canvas text-slate-500 border border-hairline'
                        )}
                      >
                        {isCompleted ? (
                          <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                        ) : isActive ? (
                          <Loader2 className="w-3.5 h-3.5 flex-shrink-0 animate-spin" />
                        ) : (
                          <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                        )}
                        <span className="min-w-0 truncate">{stage.label}</span>
                      </div>
                    </div>
                  );
                })}
                </div>
              </div>
            )}

            {/* Compact pills (collapsed) */}
            {!dispatchExpanded && allActivities.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {allActivities.map((activity) => {
                  const agent = getAgentInfo(activity.agentId);
                  return (
                    <button
                      key={activity.id}
                      onClick={() => setDispatchExpanded(true)}
                      className={clsx(
                        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium',
                        'border transition-colors cursor-pointer',
                        activity.status === 'running'
                          ? 'bg-blue-50 border-blue-200 text-blue-700'
                          : activity.status === 'completed'
                          ? 'bg-green-50 border-green-200 text-green-700'
                          : 'bg-red-50 border-red-200 text-red-700'
                      )}
                    >
                      <span>{agent.emoji}</span>
                      <span>{agent.name}</span>
                      {activity.status === 'running' && <Loader2 className="w-3 h-3 animate-spin" />}
                      {activity.status === 'completed' && <CheckCircle2 className="w-3 h-3" />}
                      {activity.status === 'failed' && <XCircle className="w-3 h-3" />}
                    </button>
                  );
                })}
              </div>
            )}

            {/* Expanded detail list */}
            {dispatchExpanded && (
              <div className="mt-2 max-h-48 space-y-1.5 overflow-y-auto overflow-x-hidden">
                {allActivities.length === 0 && isStreaming && (
                  <div className="flex items-center gap-2 px-3 py-2 text-xs text-slate border border-dashed border-hairline rounded-lg bg-canvas/50">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
                    <span>等待 CEO 分析任务…</span>
                  </div>
                )}
                {allActivities.map((activity) => {
                  const agent = getAgentInfo(activity.agentId);
                  const isItemExpanded = dispatchItemExpanded === activity.id;
                  return (
                    <div
                      key={activity.id}
                      className="border border-hairline rounded-lg bg-canvas overflow-hidden"
                    >
                      <button
                        onClick={() => setDispatchItemExpanded(isItemExpanded ? null : activity.id)}
                        className="flex w-full min-w-0 items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-surface/50"
                      >
                        <span className="text-sm">{agent.emoji}</span>
                        <span className="flex-1 text-xs font-medium text-ink truncate">
                          {agent.name}
                        </span>
                        <span className="min-w-0 max-w-[35%] truncate text-[10px] text-slate">
                          {activity.task.slice(0, 40)}{activity.task.length > 40 ? '...' : ''}
                        </span>
                        {activity.status === 'running' && <Loader2 className="w-3 h-3 animate-spin text-blue-500" />}
                        {activity.status === 'completed' && <CheckCircle2 className="w-3 h-3 text-green-500" />}
                        {activity.status === 'failed' && <XCircle className="w-3 h-3 text-red-500" />}
                      </button>
                      {isItemExpanded && (
                        <div className="px-3 pb-2 border-t border-hairline">
                          <div className="mt-1.5">
                            <p className="text-[10px] font-medium text-slate uppercase mb-0.5">任务</p>
                            <p className="text-[11px] text-ink">{activity.task}</p>
                          </div>
                          {activity.result && (
                            <div className="mt-1.5">
                              <p className="text-[10px] font-medium text-slate uppercase mb-0.5">结果</p>
                              <p className="text-[11px] text-ink line-clamp-3">
                                {activity.result.slice(0, 200)}{activity.result.length > 200 ? '...' : ''}
                              </p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
