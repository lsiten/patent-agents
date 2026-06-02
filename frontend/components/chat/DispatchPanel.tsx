'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { CheckCircle2, XCircle, Loader2, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import { clsx } from 'clsx';

export interface DispatchActivity {
  id: string;
  agentId: string;
  agentName: string;
  task: string;
  status: 'running' | 'completed' | 'failed';
  result?: string;
  startedAt: string;
  completedAt?: string;
}

interface DispatchPanelProps {
  activities: DispatchActivity[];
  workflowTaskId?: string | null;
  isActive: boolean;
}

const agentDisplay: Record<string, { name: string; emoji: string }> = {
  brainstorm_partner: { name: '头脑风暴', emoji: '💡' },
  requirement_analyst: { name: '需求分析', emoji: '🧠' },
  retrieval_analyst: { name: '检索分析', emoji: '🔍' },
  patent_writer: { name: '专利撰写', emoji: '✍️' },
  quality_reviewer: { name: '质量审查', emoji: '✅' },
};

function getAgentInfo(agentId: string) {
  return agentDisplay[agentId] || { name: agentId, emoji: '🤖' };
}

function StatusIcon({ status }: { status: DispatchActivity['status'] }) {
  if (status === 'running') return <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />;
  if (status === 'completed') return <CheckCircle2 className="w-3 h-3 text-green-500" />;
  return <XCircle className="w-3 h-3 text-red-500" />;
}

export function DispatchPanel({ activities, workflowTaskId, isActive }: DispatchPanelProps) {
  const router = useRouter();
  const [expanded, setExpanded] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Show panel when: (a) there are activities OR (b) streaming is active OR (c) a workflow is linked
  if (activities.length === 0 && !isActive && !workflowTaskId) return null;

  const runningCount = activities.filter((a) => a.status === 'running').length;
  const completedCount = activities.filter((a) => a.status === 'completed').length;
  const failedCount = activities.filter((a) => a.status === 'failed').length;

  return (
    <div className="border-b border-hairline bg-surface/80 backdrop-blur-sm px-6 py-2">
      <div className="max-w-4xl mx-auto">
        {/* Summary bar */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate">CEO 调度</span>
            {activities.length === 0 && isActive && (
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

          <div className="flex items-center gap-2">
            {workflowTaskId && (
              <button
                onClick={() => router.push(`/workflow/${encodeURIComponent(workflowTaskId)}`)}
                className="inline-flex items-center gap-1 text-[11px] text-brand-green-dark hover:underline"
              >
                <ExternalLink className="w-3 h-3" />
                详情
              </button>
            )}
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-0.5 rounded hover:bg-canvas transition-colors"
              title={expanded ? '收起' : '展开'}
            >
              {expanded ? (
                <ChevronUp className="w-3.5 h-3.5 text-slate" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 text-slate" />
              )}
            </button>
          </div>
        </div>

        {/* Compact pills */}
        {!expanded && activities.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {activities.map((activity) => {
              const agent = getAgentInfo(activity.agentId);
              return (
                <button
                  key={activity.id}
                  onClick={() => {
                    setExpanded(true);
                    setExpandedId(activity.id);
                  }}
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
                  <StatusIcon status={activity.status} />
                </button>
              );
            })}
          </div>
        )}

        {/* Expanded detail list */}
        {expanded && (
          <div className="mt-2 space-y-1.5 max-h-56 overflow-y-auto">
            {activities.length === 0 && isActive && (
              <div className="flex items-center gap-2 px-3 py-2 text-xs text-slate border border-dashed border-hairline rounded-lg bg-canvas/50">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
                <span>等待 CEO 分析任务…</span>
              </div>
            )}
            {activities.map((activity) => {
              const agent = getAgentInfo(activity.agentId);
              const isItemExpanded = expandedId === activity.id;
              return (
                <div
                  key={activity.id}
                  className="border border-hairline rounded-lg bg-canvas overflow-hidden"
                >
                  <button
                    onClick={() => setExpandedId(isItemExpanded ? null : activity.id)}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-surface/50 transition-colors"
                  >
                    <span className="text-sm">{agent.emoji}</span>
                    <span className="flex-1 text-xs font-medium text-ink truncate">
                      {agent.name}
                    </span>
                    <span className="text-[10px] text-slate truncate max-w-[200px]">
                      {activity.task.slice(0, 40)}{activity.task.length > 40 ? '...' : ''}
                    </span>
                    <StatusIcon status={activity.status} />
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
  );
}
