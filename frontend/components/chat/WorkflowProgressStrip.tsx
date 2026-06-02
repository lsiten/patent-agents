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
  ChevronRight,
  ExternalLink,
  ChevronDown,
  ChevronUp,
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
    matchStates: ['reviewing', 'quality_review', 'iteration'],
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

  let activeIndex = STAGES.findIndex((s) =>
    s.matchStates.includes(currentState ?? '')
  );
  if (activeIndex === -1) {
    if (currentState === 'completed') {
      activeIndex = STAGES.length;
    } else if (currentState === 'failed' || currentState === 'cancelled') {
      activeIndex = STAGES.findIndex((s) =>
        s.matchStates.some((m) => completedSet.has(m))
      );
      if (activeIndex === -1) activeIndex = 0;
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

  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;

    const fetchWorkflow = async () => {
      try {
        const workflow = await workflowApi.get(taskId);
        if (cancelled) return;
        setPhaseHistory(workflow.phase_history || []);
        setLatestState(workflow.current_state);
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

  const showDispatch = dispatchActivities.length > 0 || isStreaming;

  // Hide the panel entirely if nothing to show
  if (!taskId && !showDispatch) return null;

  const { activeIndex, completedSet } = resolveStageIndex(latestState, phaseHistory);
  const isTerminal = latestState === 'completed' || latestState === 'failed' || latestState === 'cancelled';

  const runningCount = dispatchActivities.filter((a) => a.status === 'running').length;
  const completedCount = dispatchActivities.filter((a) => a.status === 'completed').length;
  const failedCount = dispatchActivities.filter((a) => a.status === 'failed').length;

  return (
    <div className="border-b border-hairline bg-canvas/60">
      {/* 4-Stage Progress Strip (only when workflow is linked) */}
      {taskId && (
        <div className="px-6 py-2.5 border-b border-hairline/60">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-slate">专利申请流程</span>
                {latestState === 'completed' && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-green-600">
                    <CheckCircle2 className="w-3 h-3" />
                    已完成
                  </span>
                )}
                {latestState === 'failed' && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-red-600">
                    <XCircle className="w-3 h-3" />
                    失败
                  </span>
                )}
                {latestState === 'cancelled' && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-orange-600">
                    <XCircle className="w-3 h-3" />
                    已取消
                  </span>
                )}
                {!isTerminal && latestState && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-blue-600">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    流程进行中
                  </span>
                )}
              </div>
              <button
                onClick={() => router.push(`/workflow/${encodeURIComponent(taskId)}`)}
                className="inline-flex items-center gap-1 text-[11px] text-brand-green-dark hover:underline"
              >
                <ExternalLink className="w-3 h-3" />
                详情
              </button>
            </div>

            <div className="flex items-center gap-1">
              {STAGES.map((stage, idx) => {
                const isCompleted = idx < activeIndex ||
                  STAGES.slice(0, idx).every((s) =>
                    s.matchStates.some((m) => completedSet.has(m))
                  );
                const isActive = idx === activeIndex && !isTerminal;
                const Icon = stage.icon;

                return (
                  <div key={stage.id} className="flex items-center flex-1 min-w-0">
                    <div
                      className={clsx(
                        'flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium transition-colors w-full',
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
                      <span className="truncate">{stage.label}</span>
                    </div>
                    {idx < STAGES.length - 1 && (
                      <ChevronRight className="w-3 h-3 mx-0.5 text-slate-300 flex-shrink-0" />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* CEO Dispatch Section */}
      {showDispatch && (
        <div className="px-6 py-2">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-slate">CEO 调度</span>
                {dispatchActivities.length === 0 && isStreaming && (
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

            {/* Compact pills (collapsed) */}
            {!dispatchExpanded && dispatchActivities.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {dispatchActivities.map((activity) => {
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
              <div className="mt-2 space-y-1.5 max-h-48 overflow-y-auto">
                {dispatchActivities.length === 0 && isStreaming && (
                  <div className="flex items-center gap-2 px-3 py-2 text-xs text-slate border border-dashed border-hairline rounded-lg bg-canvas/50">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
                    <span>等待 CEO 分析任务…</span>
                  </div>
                )}
                {dispatchActivities.map((activity) => {
                  const agent = getAgentInfo(activity.agentId);
                  const isItemExpanded = dispatchItemExpanded === activity.id;
                  return (
                    <div
                      key={activity.id}
                      className="border border-hairline rounded-lg bg-canvas overflow-hidden"
                    >
                      <button
                        onClick={() => setDispatchItemExpanded(isItemExpanded ? null : activity.id)}
                        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-surface/50 transition-colors"
                      >
                        <span className="text-sm">{agent.emoji}</span>
                        <span className="flex-1 text-xs font-medium text-ink truncate">
                          {agent.name}
                        </span>
                        <span className="text-[10px] text-slate truncate max-w-[200px]">
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
