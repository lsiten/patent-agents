'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { clsx } from 'clsx';
import type { AgentLogEntry } from '@/types';

const agentIcons: Record<string, string> = {
  'CEO Agent': '👨‍💼',
  '需求分析 Agent': '🧠',
  '检索分析 Agent': '🔍',
  '专利撰写 Agent': '✍️',
  '质量审查 Agent': '✅',
};

function getAgentIcon(name: string): string {
  return agentIcons[name] || '🤖';
}

function formatTime(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return '';
  }
}

function DispatchEntry({ entry }: { entry: AgentLogEntry }) {
  return (
    <div className="pl-6 border-l-2 border-brand-green/40">
      <span className="text-brand-green font-medium">🎯 调度 → {entry.dispatch_to}</span>
      {entry.dispatch_task && (
        <p className="text-on-dark-muted text-xs mt-0.5 truncate max-w-[500px]">
          &quot;{entry.dispatch_task}&quot;
        </p>
      )}
    </div>
  );
}

function ThinkingEntry({ entry }: { entry: AgentLogEntry }) {
  return (
    <div className="pl-6 border-l-2 border-slate-600/40">
      <span className="text-slate-300 italic text-xs">
        💭 {entry.message}
      </span>
    </div>
  );
}

function ToolStartEntry({ entry }: { entry: AgentLogEntry }) {
  return (
    <div className="pl-6 border-l-2 border-amber-500/40">
      <span className="text-amber-400 text-xs font-mono">
        🔧 调用工具: <span className="font-semibold">{entry.tool_name}</span>
      </span>
      {entry.tool_params && Object.keys(entry.tool_params).length > 0 && (
        <p className="text-on-dark-muted text-xs mt-0.5 font-mono truncate max-w-[500px]">
          参数: {JSON.stringify(entry.tool_params)}
        </p>
      )}
    </div>
  );
}

function ToolEndEntry({ entry }: { entry: AgentLogEntry }) {
  const isSuccess = entry.tool_success !== false;
  return (
    <div className="pl-10 border-l-2 border-amber-500/40">
      <span className={clsx('text-xs font-mono', isSuccess ? 'text-emerald-400' : 'text-red-400')}>
        {isSuccess ? '✅' : '❌'} 返回: {entry.tool_result ? entry.tool_result.slice(0, 200) : '(空)'}
      </span>
    </div>
  );
}

function ContentEntry({ entry }: { entry: AgentLogEntry }) {
  return (
    <div className="pl-6 border-l-2 border-blue-500/40">
      <span className="text-blue-300 text-xs">📄 输出:</span>
      <p className="text-on-dark text-sm mt-0.5 whitespace-pre-wrap line-clamp-4">
        {entry.content}
      </p>
    </div>
  );
}

function ProgressEntry({ entry }: { entry: AgentLogEntry }) {
  return (
    <div className="pl-6 border-l-2 border-brand-green/40">
      <span className="text-brand-green text-xs">
        ⏱️ {entry.message}
      </span>
    </div>
  );
}

function ErrorEntry({ entry }: { entry: AgentLogEntry }) {
  return (
    <div className="pl-6 border-l-2 border-red-500/40">
      <span className="text-red-400 text-xs">
        ⚠️ {entry.message}
      </span>
    </div>
  );
}

function LogEntryContent({ entry }: { entry: AgentLogEntry }) {
  switch (entry.type) {
    case 'dispatch':
      return <DispatchEntry entry={entry} />;
    case 'thinking':
      return <ThinkingEntry entry={entry} />;
    case 'tool_start':
      return <ToolStartEntry entry={entry} />;
    case 'tool_end':
      return <ToolEndEntry entry={entry} />;
    case 'content':
      return <ContentEntry entry={entry} />;
    case 'progress':
      return <ProgressEntry entry={entry} />;
    case 'error':
      return <ErrorEntry entry={entry} />;
    default:
      return null;
  }
}

interface AgentTerminalLogProps {
  entries: AgentLogEntry[];
  className?: string;
}

export function AgentTerminalLog({ entries, className }: AgentTerminalLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [activeFilter, setActiveFilter] = useState<string>('all');

  // 提取所有出现过的agent名称
  const agentNames = useMemo(() => {
    const names = new Set<string>();
    for (const entry of entries) {
      if (entry.agent_name) names.add(entry.agent_name);
    }
    return Array.from(names);
  }, [entries]);

  // 过滤后的日志
  const filteredEntries = useMemo(() => {
    if (activeFilter === 'all') return entries;
    return entries.filter((e) => e.agent_name === activeFilter);
  }, [entries, activeFilter]);

  // 自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredEntries.length]);

  // 按agent分组连续条目，以便显示agent header
  const shouldShowHeader = (entry: AgentLogEntry, index: number): boolean => {
    if (index === 0) return true;
    const prev = filteredEntries[index - 1];
    // tool_end 紧跟 tool_start 不显示header
    if (entry.type === 'tool_end') return false;
    return prev.agent_name !== entry.agent_name;
  };

  return (
    <div className={clsx('flex flex-col', className)}>
      {/* Agent 过滤栏 */}
      {agentNames.length > 0 && (
        <div className="flex items-center gap-1.5 mb-3 flex-wrap">
          <button
            onClick={() => setActiveFilter('all')}
            className={clsx(
              'px-2.5 py-1 rounded-full text-xs font-medium transition-colors',
              activeFilter === 'all'
                ? 'bg-brand-green text-ink'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            )}
          >
            全部
          </button>
          {agentNames.map((name) => (
            <button
              key={name}
              onClick={() => setActiveFilter(name)}
              className={clsx(
                'px-2.5 py-1 rounded-full text-xs font-medium transition-colors inline-flex items-center gap-1',
                activeFilter === name
                  ? 'bg-brand-green text-ink'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              )}
            >
              <span>{getAgentIcon(name)}</span>
              {name}
            </button>
          ))}
        </div>
      )}

      {/* 日志内容 */}
      <div
        ref={scrollRef}
        className="bg-canvas-dark rounded-lg p-lg max-h-[600px] overflow-y-auto font-mono text-sm"
      >
        {filteredEntries.length === 0 ? (
          <div className="text-center py-xl text-on-dark-muted">
            <p className="text-sm">
              {entries.length === 0 ? '等待工作流启动...' : '当前过滤无结果'}
            </p>
            <p className="text-xs mt-1 opacity-60">
              {entries.length === 0
                ? 'Agent 执行过程将在此实时显示'
                : '切换过滤条件查看其他 Agent 日志'}
            </p>
          </div>
        ) : (
          <div className="space-y-1.5">
            {filteredEntries.map((entry, index) => (
              <div key={entry.id}>
                {shouldShowHeader(entry, index) && (
                  <div className="flex items-center gap-2 mt-3 mb-1 first:mt-0">
                    <span className="text-lg">{getAgentIcon(entry.agent_name)}</span>
                    <span className="text-on-dark font-semibold text-xs">
                      {entry.agent_name}
                    </span>
                    <span className="text-on-dark-muted text-micro">
                      {formatTime(entry.timestamp)}
                    </span>
                  </div>
                )}
                <LogEntryContent entry={entry} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
