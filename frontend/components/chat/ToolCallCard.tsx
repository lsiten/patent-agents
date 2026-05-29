'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, CheckCircle2, XCircle, Zap, Sparkles, Loader2 } from 'lucide-react';

interface ToolCallInfo {
  name: string;
  parameters: Record<string, unknown>;
  result: unknown;
  success: boolean;
  error?: string;
  duration_ms?: number;
}

interface SkillUseInfo {
  name: string;
  description: string;
  reasoning: string;
}

interface ToolCallCardProps {
  toolCalls?: ToolCallInfo[];
  skillUses?: SkillUseInfo[];
  isStreaming?: boolean;
}

const toolDisplayNames: Record<string, { label: string; icon: string }> = {
  task_planner: { label: '任务规划', icon: '📋' },
  agent_selector: { label: 'Agent 调度', icon: '🤖' },
  quality_assessor: { label: '质量评估', icon: '✅' },
  risk_analyzer: { label: '风险分析', icon: '⚠️' },
  report_generator: { label: '报告生成', icon: '📊' },
  creative_thinking: { label: '创意激发', icon: '💡' },
  patent_strategy_guide: { label: '专利策略', icon: '🎯' },
  ipc_classifier: { label: 'IPC 分类', icon: '🏷️' },
  tech_feature_extractor: { label: '特征提取', icon: '🔬' },
  scenario_miner: { label: '场景挖掘', icon: '💎' },
  patent_search: { label: '专利检索', icon: '🔍' },
  knowledge_search: { label: '知识库搜索', icon: '📚' },
};

const skillDisplayIcons: Record<string, string> = {
  '创意激发': '💡',
  '技术分析': '🔬',
  '风险评估': '⚠️',
  '保护方向探索': '🧭',
  'IPC分类': '🏷️',
  '专利性判断': '⚖️',
  '现有技术对比': '🔍',
  '商业价值分析': '💰',
  '权利要求设计': '📝',
  'Agent调度': '🤖',
};

function getToolDisplay(name: string) {
  return toolDisplayNames[name] || { label: name, icon: '🔧' };
}

function SingleToolCall({ tool }: { tool: ToolCallInfo }) {
  const [expanded, setExpanded] = useState(false);
  const display = getToolDisplay(tool.name);
  const isLoading = tool.result === null && tool.success;

  return (
    <div className="border border-hairline rounded-lg overflow-hidden bg-surface/50">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-surface transition-colors"
      >
        <span className="text-sm">{display.icon}</span>
        <span className="flex-1 text-xs font-medium text-ink truncate">
          {display.label}
        </span>
        {isLoading ? (
          <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin flex-shrink-0" />
        ) : tool.success ? (
          <CheckCircle2 className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
        ) : (
          <XCircle className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />
        )}
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-slate flex-shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-slate flex-shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-3 border-t border-hairline">
          {tool.parameters && Object.keys(tool.parameters).length > 0 && (
            <div className="mt-2">
              <p className="text-[10px] font-medium text-slate uppercase tracking-wide mb-1">参数</p>
              <pre className="text-[11px] text-ink bg-canvas rounded p-2 overflow-x-auto max-h-32 overflow-y-auto">
                {JSON.stringify(tool.parameters, null, 2)}
              </pre>
            </div>
          )}

          {tool.success && tool.result != null && (
            <div className="mt-2">
              <p className="text-[10px] font-medium text-slate uppercase tracking-wide mb-1">结果</p>
              <pre className="text-[11px] text-ink bg-canvas rounded p-2 overflow-x-auto max-h-48 overflow-y-auto">
                {typeof tool.result === 'string'
                  ? tool.result
                  : JSON.stringify(tool.result, null, 2)}
              </pre>
            </div>
          )}

          {!tool.success && tool.error && (
            <div className="mt-2">
              <p className="text-[10px] font-medium text-red-500 uppercase tracking-wide mb-1">错误</p>
              <pre className="text-[11px] text-red-600 bg-red-50 rounded p-2 overflow-x-auto">
                {tool.error}
              </pre>
            </div>
          )}

          {isLoading && (
            <div className="mt-2 flex items-center gap-2 text-xs text-slate">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>执行中...</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SingleSkillUse({ skill }: { skill: SkillUseInfo }) {
  const [expanded, setExpanded] = useState(false);
  const icon = skillDisplayIcons[skill.name] || '✨';

  return (
    <div className="border border-purple-200 rounded-lg overflow-hidden bg-purple-50/30">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-purple-50/50 transition-colors"
      >
        <span className="text-sm">{icon}</span>
        <span className="flex-1 text-xs font-medium text-purple-800 truncate">
          {skill.name}
        </span>
        <Sparkles className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-3 border-t border-purple-200">
          {skill.description && (
            <div className="mt-2">
              <p className="text-[10px] font-medium text-purple-600 uppercase tracking-wide mb-1">说明</p>
              <p className="text-[11px] text-purple-800">{skill.description}</p>
            </div>
          )}
          {skill.reasoning && (
            <div className="mt-2">
              <p className="text-[10px] font-medium text-purple-600 uppercase tracking-wide mb-1">推理</p>
              <p className="text-[11px] text-purple-800">{skill.reasoning}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ToolCallCard({ toolCalls, skillUses, isStreaming }: ToolCallCardProps) {
  const hasTools = toolCalls && toolCalls.length > 0;
  const hasSkills = skillUses && skillUses.length > 0;

  if (!hasTools && !hasSkills) return null;

  return (
    <div className="mt-2 space-y-2">
      {hasSkills && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-[11px] text-purple-600">
            <Sparkles className="w-3 h-3" />
            <span>使用了 {skillUses!.length} 项技能</span>
          </div>
          <div className="space-y-1">
            {skillUses!.map((skill, index) => (
              <SingleSkillUse key={`${skill.name}-${index}`} skill={skill} />
            ))}
          </div>
        </div>
      )}

      {hasTools && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-[11px] text-slate">
            <Zap className="w-3 h-3" />
            <span>调用了 {toolCalls!.length} 个工具</span>
            {isStreaming && <Loader2 className="w-3 h-3 animate-spin text-blue-500" />}
          </div>
          <div className="space-y-1">
            {toolCalls!.map((tool, index) => (
              <SingleToolCall key={`${tool.name}-${index}`} tool={tool} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
