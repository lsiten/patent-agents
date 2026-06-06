'use client';

import { useState, useRef, useEffect } from 'react';
import {
  Brain,
  Zap,
  CheckCircle2,
  Loader2,
  Info,
  ChevronDown,
  ChevronRight,
  Timer,
} from 'lucide-react';
import type { AgentEvent } from '@/types';

interface AgentActivityLogProps {
  events: AgentEvent[];
  className?: string;
}

const eventIcons: Record<string, React.ReactNode> = {
  thinking: <Brain className="w-3 h-3 text-purple-500" />,
  tool_call_start: <Zap className="w-3 h-3 text-amber-500" />,
  tool_call_end: <CheckCircle2 className="w-3 h-3 text-green-500" />,
  status: <Info className="w-3 h-3 text-blue-500" />,
};

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

function getEventMessage(event: AgentEvent): string {
  if (event.message) return event.message;
  switch (event.type) {
    case 'thinking':
      return '思考中...';
    case 'tool_call_start':
      return `调用工具: ${event.data?.name ?? 'unknown'}`;
    case 'tool_call_end':
      return `工具完成: ${event.data?.name ?? 'unknown'}`;
    default:
      return event.type;
  }
}

export function AgentActivityLog({ events, className = '' }: AgentActivityLogProps) {
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (expanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, expanded]);

  if (events.length === 0) return null;

  const runningCount = events.filter(
    (e) => e.type === 'tool_call_start'
  ).length;
  const doneCount = events.filter((e) => e.type === 'tool_call_end').length;

  return (
    <div className={`mt-2 rounded-xl border border-hairline bg-surface/70 ${className}`}>
      {/* Summary bar */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left transition-colors hover:bg-canvas focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green/40"
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-slate" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-slate" />
        )}
        <Timer className="h-3.5 w-3.5 text-slate/70" />
        <span className="text-xs font-medium text-slate">Agent 活动日志</span>
        <span className="text-[11px] text-slate/60">
          {events.length} 条事件
        </span>
        {runningCount > doneCount && (
          <span className="inline-flex items-center gap-1 text-[11px] text-amber-600 ml-auto">
            <Loader2 className="w-3 h-3 animate-spin" />
            {runningCount - doneCount} 进行中
          </span>
        )}
      </button>

      {/* Event list */}
      {expanded && (
        <div
          ref={scrollRef}
          className="max-h-48 space-y-0.5 overflow-y-auto border-t border-hairline px-3 py-2"
        >
          {events.map((event, idx) => (
            <div
              key={event.id || `${event.type}-${idx}-${event.timestamp}`}
              className="flex items-start gap-2 rounded-md px-1 py-0.5 text-[11px] leading-relaxed hover:bg-canvas/70"
            >
              <span className="flex-shrink-0 mt-0.5">
                {event.type === 'tool_call_start' ? (
                  <Loader2 className="w-3 h-3 text-amber-500 animate-spin" />
                ) : (
                  eventIcons[event.type] || (
                    <Info className="w-3 h-3 text-slate" />
                  )
                )}
              </span>
              <span className="text-slate/70 flex-shrink-0 font-mono">
                {formatTime(event.timestamp)}
              </span>
              <span className="text-ink/80 flex-1 min-w-0 truncate">
                {getEventMessage(event)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
