'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { clsx } from 'clsx';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { AgentLogEntry } from '@/types';

// 可展开的文本组件
function ExpandableText({ 
  text, 
  maxLength = 200,
  className = '' 
}: { 
  text: string; 
  maxLength?: number;
  className?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const needsExpand = text.length > maxLength;
  
  if (!needsExpand) {
    return <span className={className}>{text}</span>;
  }
  
  return (
    <span className={className}>
      {expanded ? text : `${text.slice(0, maxLength)}...`}
      <button
        onClick={() => setExpanded(!expanded)}
        className="ml-1 text-brand-green hover:text-brand-green-dark text-xs underline"
      >
        {expanded ? '收起' : '展开'}
      </button>
    </span>
  );
}

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
    <div className="min-w-0 break-words border-l-2 border-brand-green/40 pl-6">
      <span className="font-medium text-brand-green">🎯 调度 → {entry.dispatch_to}</span>
      {entry.dispatch_task && (
        <p className="text-on-dark-muted text-xs mt-0.5">
          <ExpandableText text={`"${entry.dispatch_task}"`} maxLength={100} />
        </p>
      )}
    </div>
  );
}

function ThinkingEntry({ entry }: { entry: AgentLogEntry }) {
  return (
    <div className="min-w-0 break-words border-l-2 border-on-dark-muted/40 pl-6">
      <span className="text-on-dark-muted italic text-xs">
        💭 {entry.message}
      </span>
    </div>
  );
}

function ToolStartEntry({ entry }: { entry: AgentLogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const paramsStr = entry.tool_params && Object.keys(entry.tool_params).length > 0 
    ? JSON.stringify(entry.tool_params, null, 2) 
    : '';
  const needsExpand = paramsStr.length > 100;

  return (
    <div className="min-w-0 border-l-2 border-amber-500/40 pl-6">
      <div className="flex min-w-0 items-center gap-1">
        <span className="min-w-0 break-words font-mono text-xs text-amber-400">
          🔧 调用工具: <span className="font-semibold">{entry.tool_name}</span>
        </span>
        {needsExpand && (
          <button 
            onClick={() => setExpanded(!expanded)}
            className="text-amber-400/70 hover:text-amber-400"
          >
            {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
        )}
      </div>
      {paramsStr && (
        <pre className={clsx(
          'text-on-dark-muted text-xs mt-0.5 font-mono whitespace-pre-wrap break-all min-w-0',
          !expanded && needsExpand && 'line-clamp-2'
        )}>
          参数: {paramsStr}
        </pre>
      )}
    </div>
  );
}

function ToolEndEntry({ entry }: { entry: AgentLogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const isSuccess = entry.tool_success !== false;
  const result = entry.tool_result || '(空)';
  const needsExpand = result.length > 150;

  return (
    <div className="min-w-0 border-l-2 border-amber-500/40 pl-10">
      <div className="flex min-w-0 items-center gap-1">
        <span className={clsx('text-xs font-mono', isSuccess ? 'text-emerald-400' : 'text-red-400')}>
          {isSuccess ? '✅' : '❌'} 返回:
        </span>
        {needsExpand && (
          <button 
            onClick={() => setExpanded(!expanded)}
            className={clsx(
              'hover:opacity-80',
              isSuccess ? 'text-emerald-400/70' : 'text-red-400/70'
            )}
          >
            {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
        )}
      </div>
      <pre className={clsx(
        'text-xs font-mono whitespace-pre-wrap break-all mt-0.5 min-w-0',
        isSuccess ? 'text-emerald-300/80' : 'text-red-300/80',
        !expanded && needsExpand && 'line-clamp-3'
      )}>
        {result}
      </pre>
    </div>
  );
}

function ContentEntry({ entry }: { entry: AgentLogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const content = entry.content || '';
  const needsExpand = content.length > 300 || content.split('\n').length > 4;

  return (
    <div className="min-w-0 border-l-2 border-blue-500/40 pl-6">
      <div className="flex min-w-0 items-center gap-1">
        <span className="text-blue-300 text-xs">📄 输出:</span>
        {needsExpand && (
          <button 
            onClick={() => setExpanded(!expanded)}
            className="text-blue-300/70 hover:text-blue-300"
          >
            {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
        )}
      </div>
      <p className={clsx(
        'text-white text-sm mt-0.5 whitespace-pre-wrap break-words',
        !expanded && needsExpand && 'line-clamp-4'
      )}>
        {content}
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

function entryMatchesAgent(entry: AgentLogEntry, agentName: string): boolean {
  return entry.agent_name === agentName || entry.dispatch_to === agentName;
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
      if (entry.dispatch_to) names.add(entry.dispatch_to);
    }
    return Array.from(names);
  }, [entries]);

  // 过滤后的日志
  const filteredEntries = useMemo(() => {
    if (activeFilter === 'all') return entries;
    return entries.filter((entry) => entryMatchesAgent(entry, activeFilter));
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
    <div className={clsx('flex min-w-0 max-w-full flex-col overflow-hidden', className)}>
      {/* Agent 过滤栏 */}
      {agentNames.length > 0 && (
        <div className="mb-3 flex min-w-0 flex-wrap items-center gap-1.5">
          <button
            onClick={() => setActiveFilter('all')}
            className={clsx(
              'px-2.5 py-1 rounded-full text-xs font-medium transition-colors',
              activeFilter === 'all'
                ? 'bg-brand-green text-ink'
                : 'bg-surface-soft text-slate hover:bg-hairline'
            )}
          >
            全部
          </button>
          {agentNames.map((name) => (
            <button
              key={name}
              onClick={() => setActiveFilter(name)}
              className={clsx(
                'inline-flex min-w-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-colors',
                activeFilter === name
                  ? 'bg-brand-green text-ink'
                  : 'bg-surface-soft text-slate hover:bg-hairline'
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
        className="max-h-[600px] min-w-0 max-w-full overflow-y-auto overflow-x-hidden rounded-lg bg-canvas-dark p-lg font-mono text-sm"
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
          <div className="min-w-0 space-y-1.5">
            {filteredEntries.map((entry, index) => (
              <div key={entry.id}>
                {shouldShowHeader(entry, index) && (
                  <div className="flex items-center gap-2 mt-3 mb-1 first:mt-0">
                    <span className="text-lg">{getAgentIcon(entry.agent_name)}</span>
                    <span className="text-white font-semibold text-xs">
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
