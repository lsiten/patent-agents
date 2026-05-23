'use client';

import { Brain, Search, FileEdit, CheckSquare, User } from 'lucide-react';
import { clsx } from 'clsx';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';

export type AgentStatus = 'idle' | 'working' | 'completed' | 'error';

interface AgentInfo {
  id: string;
  name: string;
  role: string;
  description: string;
  status: AgentStatus;
  currentTask?: string;
}

const iconMap: Record<string, React.ReactNode> = {
  ceo: <User className="w-5 h-5" />,
  requirement: <Brain className="w-5 h-5" />,
  retrieval: <Search className="w-5 h-5" />,
  writer: <FileEdit className="w-5 h-5" />,
  reviewer: <CheckSquare className="w-5 h-5" />,
};

const statusColors: Record<AgentStatus, string> = {
  idle: 'bg-slate-100 text-slate-500',
  working: 'bg-brand-green-soft text-brand-green-dark',
  completed: 'bg-green-100 text-green-700',
  error: 'bg-red-100 text-red-700',
};

const statusLabels: Record<AgentStatus, string> = {
  idle: '等待中',
  working: '处理中',
  completed: '已完成',
  error: '出错',
};

interface AgentCardProps {
  agent: AgentInfo;
  className?: string;
}

export function AgentCard({ agent, className }: AgentCardProps) {
  return (
    <Card className={clsx('transition-all duration-300', className)}>
      <div className="flex items-start gap-4">
        {/* Icon */}
        <div
          className={clsx(
            'w-12 h-12 rounded-xl flex items-center justify-center',
            agent.status === 'working'
              ? 'bg-brand-green text-ink animate-pulse'
              : agent.status === 'completed'
                ? 'bg-green-100 text-green-700'
                : 'bg-slate-100 text-slate-400'
          )}
        >
          {iconMap[agent.id] || <Brain className="w-5 h-5" />}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-semibold text-ink text-base">{agent.name}</h3>
            <Badge variant="soft" color={agent.status === 'error' ? 'orange' : 'green'}>
              <span className={clsx('text-xs font-medium', statusColors[agent.status])}>
                {statusLabels[agent.status]}
              </span>
            </Badge>
          </div>
          <p className="text-sm text-steel mb-1">{agent.role}</p>
          <p className="text-xs text-muted">{agent.description}</p>

          {agent.status === 'working' && agent.currentTask && (
            <div className="mt-3 p-2 rounded-md bg-brand-green-soft/50">
              <p className="text-xs text-brand-green-dark">
                🚀 {agent.currentTask}
              </p>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
