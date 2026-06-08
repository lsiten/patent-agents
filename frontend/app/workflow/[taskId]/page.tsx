'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Brain,
  Search,
  FileEdit,
  CheckSquare,
  User,
  ChevronRight,
  AlertCircle,
  RefreshCw,
  Pause,
  Play,
  MessageSquare,
  Download,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Textarea } from '@/components/ui/Textarea';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs';
import { CodeBlock } from '@/components/ui/CodeBlock';
import { workflowApi, type WorkflowResponse } from '@/lib/api';
import type { WorkflowState, AgentInfo, AgentLogEntry } from '@/types';
import {
  RequirementAnalysisView,
  RetrievalReportView,
  PatentDraftView,
  QualityReviewView,
  MultiRoundView,
} from '@/components/workflow/AgentOutputRenderers';
import { AgentTerminalLog } from '@/components/workflow/AgentTerminalLog';

const workflowSteps: { state: WorkflowState; label: string; icon: typeof Brain }[] = [
  { state: 'initial', label: '已提交', icon: User },
  { state: 'requirement', label: '需求分析', icon: Brain },
  { state: 'retrieval', label: '检索分析', icon: Search },
  { state: 'writing', label: '文件撰写', icon: FileEdit },
  { state: 'reviewing', label: '质量审查', icon: CheckSquare },
  { state: 'awaiting_user_decision', label: '待补充信息', icon: MessageSquare },
  { state: 'completed', label: '完成', icon: CheckSquare },
];

const stateMap: Record<string, WorkflowState> = {
  initialized: 'initial',
  brainstorming: 'initial',
  brainstorm: 'initial',
  requirement_analysis: 'requirement',
  requirement: 'requirement',
  retrieval_analysis: 'retrieval',
  retrieval: 'retrieval',
  patent_writing: 'writing',
  writing: 'writing',
  quality_review: 'reviewing',
  review: 'reviewing',
  iteration: 'reviewing',
  awaiting_user_decision: 'awaiting_user_decision',
  completed: 'completed',
  failed: 'failed',
  cancelled: 'failed',
};

const phaseAgentMap: Record<string, string> = {
  brainstorming: '专利头脑风暴 Agent',
  brainstorm: '专利头脑风暴 Agent',
  requirement_analysis: '需求分析 Agent',
  requirement: '需求分析 Agent',
  retrieval_analysis: '检索分析 Agent',
  retrieval: '检索分析 Agent',
  patent_writing: '专利撰写 Agent',
  writing: '专利撰写 Agent',
  quality_review: '质量审查 Agent',
  review: '质量审查 Agent',
};

const terminalStates = new Set(['completed', 'failed', 'cancelled']);

function getWorkflowState(workflow: WorkflowResponse | null): WorkflowState {
  if (!workflow) return 'initial';
  return stateMap[workflow.current_state] ?? 'initial';
}

function hasOutput(output: Record<string, unknown> | undefined): boolean {
  return Boolean(output && Object.keys(output).length > 0);
}

function getAgentStatus(
  agentState: WorkflowState,
  currentState: WorkflowState,
  workflow: WorkflowResponse | null
): AgentInfo['status'] {
  if (!workflow) return 'idle';
  
  // 映射 agentState 到 phase 名称（注意：API 返回的 phase 名称）
  const stateToPhase: Record<WorkflowState, string> = {
    initial: 'brainstorming',
    requirement: 'requirement',
    retrieval: 'retrieval',
    writing: 'writing',
    reviewing: 'review',
    iteration: 'review',
    awaiting_user_decision: 'review',
    completed: 'completed',
    failed: 'review',
  };
  
  const agentPhase = stateToPhase[agentState];
  
  // 检查 phase_history 中是否有该阶段的记录
  const phaseResult = workflow.phase_history.find(
    (phase) => phase.phase === agentPhase
  );
  
  // 如果有历史记录，根据实际结果返回状态
  if (phaseResult) {
    return phaseResult.success ? 'completed' : 'error';
  }
  
  // 如果工作流已终止且没有该阶段记录，返回 idle
  if (terminalStates.has(workflow.current_state)) {
    return 'idle';
  }

  const currentIndex = workflowSteps.findIndex((step) => step.state === currentState);
  const agentIndex = workflowSteps.findIndex((step) => step.state === agentState);

  if (agentIndex < currentIndex || currentState === 'completed') return 'completed';
  if (agentIndex === currentIndex) return 'working';
  return 'idle';
}

function createAgents(currentState: WorkflowState, workflow: WorkflowResponse | null): AgentInfo[] {
  return [
    {
      id: 'ceo',
      name: 'CEO Agent',
      role: '统筹调度',
      description: '负责全局流程调度、冲突协调和质量把控',
      status: workflow && terminalStates.has(workflow.current_state) ? 'completed' : 'working',
      icon: '👨‍💼',
    },
    {
      id: 'requirement',
      name: '需求分析 Agent',
      role: '技术分析',
      description: '解析技术描述，提取关键创新点',
      status: getAgentStatus('requirement', currentState, workflow),
      icon: '🧠',
    },
    {
      id: 'retrieval',
      name: '检索分析 Agent',
      role: '专利性评估',
      description: '检索现有技术，评估专利性',
      status: getAgentStatus('retrieval', currentState, workflow),
      icon: '🔍',
    },
    {
      id: 'writing',
      name: '专利撰写 Agent',
      role: '文件生成',
      description: '生成符合规范的专利申请文件',
      status: getAgentStatus('writing', currentState, workflow),
      icon: '✍️',
    },
    {
      id: 'review',
      name: '质量审查 Agent',
      role: '合规校验',
      description: '审查文件质量，预判审查风险',
      status: getAgentStatus('reviewing', currentState, workflow),
      icon: '✅',
    },
  ];
}

function createHistoryLogs(workflow: WorkflowResponse | null, taskId: string): AgentLogEntry[] {
  if (!workflow) return [];

  const createdAt = new Date(workflow.created_at).getTime();
  const logs: AgentLogEntry[] = [
    {
      id: `hist_${taskId}_init`,
      timestamp: workflow.created_at,
      agent_name: 'CEO Agent',
      type: 'dispatch',
      dispatch_to: '工作流引擎',
      dispatch_task: '启动专利申请流程',
    },
  ];

  workflow.phase_history.forEach((phaseResult, index) => {
    const agentName = phaseAgentMap[phaseResult.phase] ?? 'Workflow Engine';
    const ts = new Date(createdAt + (index + 1) * 1000).toISOString();

    // CEO调度事件
    logs.push({
      id: `hist_${taskId}_dispatch_${index}`,
      timestamp: ts,
      agent_name: 'CEO Agent',
      type: 'dispatch',
      dispatch_to: agentName,
      dispatch_task: `执行${agentName}阶段任务`,
    });

    // Agent完成/失败事件
    if (phaseResult.success) {
      logs.push({
        id: `hist_${taskId}_done_${index}`,
        timestamp: new Date(createdAt + (index + 1) * 1000 + 500).toISOString(),
        agent_name: agentName,
        type: 'content',
        content: `已完成，用时 ${phaseResult.duration_seconds.toFixed(2)} 秒`,
        phase: phaseResult.phase,
      });
    } else {
      logs.push({
        id: `hist_${taskId}_err_${index}`,
        timestamp: new Date(createdAt + (index + 1) * 1000 + 500).toISOString(),
        agent_name: agentName,
        type: 'error',
        message: `执行失败${phaseResult.issues?.length ? '：' + phaseResult.issues[0] : ''}`,
      });
    }
  });

  if (!terminalStates.has(workflow.current_state)) {
    const currentLabel = workflowSteps.find((step) => step.state === getWorkflowState(workflow))?.label ?? workflow.current_state;
    logs.push({
      id: `hist_${taskId}_progress`,
      timestamp: new Date().toISOString(),
      agent_name: 'Workflow Engine',
      type: 'progress',
      message: `当前阶段：${currentLabel}`,
    });
  }

  return logs;
}

function getStatusLabel(workflow: WorkflowResponse | null): string {
  if (!workflow) return '加载中...';

  switch (workflow.current_state) {
    case 'initialized':
      return '待启动';
    case 'completed':
      return '已完成';
    case 'awaiting_user_decision':
      return '等待补充信息';
    case 'failed':
      return '已失败';
    case 'cancelled':
      return '已取消';
    default:
      return '处理中...';
  }
}

function EmptyOutput({ icon: Icon, message }: { icon: typeof Brain; message: string }) {
  return (
    <div className="text-center py-xxl text-muted">
      <Icon className="w-12 h-12 mx-auto mb-md opacity-50" />
      <p>{message}</p>
    </div>
  );
}

export default function WorkflowPage() {
  const params = useParams();
  const router = useRouter();
  const taskIdParam = params?.taskId;
  const taskId = Array.isArray(taskIdParam) ? taskIdParam[0] : taskIdParam ?? null;
  const [workflow, setWorkflow] = useState<WorkflowResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollIntervalMs, setPollIntervalMs] = useState(3000);
  const [isPaused, setIsPaused] = useState(false);
  const [agentLogs, setAgentLogs] = useState<AgentLogEntry[]>([]);
  const [supplementalInfo, setSupplementalInfo] = useState('');
  const [decisionPending, setDecisionPending] = useState(false);

  // SSE连接：监听agent级别实时事件，自动重连（指数退避）
  useEffect(() => {
    if (!taskId) return;

    const baseUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/\/+$/, '');
    const SSE_MAX_RETRIES = 8;
    const SSE_INITIAL_DELAY = 1000;
    const SSE_MAX_DELAY = 30000;

    let es: EventSource | null = null;
    let retryCount = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;
    let logIdCounter = 0;

    const createLogId = () => `log_${Date.now()}_${logIdCounter++}`;

    const addLog = (entry: Omit<AgentLogEntry, 'id'>) => {
      setAgentLogs((prev) => [...prev, { ...entry, id: createLogId() }]);
    };

    const clearEventSource = () => {
      if (es) {
        es.close();
        es = null;
      }
    };

    function connect() {
      if (closed) return;
      clearEventSource();

      es = new EventSource(`${baseUrl}/workflows/${taskId}/stream`);

      const onThinking = (e: MessageEvent) => {
        try {
          const parsed = JSON.parse(e.data);
          const data = parsed.data || parsed;
          const thought = data.thought || data.message || parsed.message || '';
          if (!thought || thought.length < 5) return;
          if (/^[{\["]/.test(thought.trim()) && thought.length < 100) return;
          addLog({
            timestamp: parsed.timestamp || new Date().toISOString(),
            agent_name: data.agent_name || parsed.agent || 'Agent',
            type: 'thinking',
            message: thought,
          });
        } catch {}
      };

      const onToolCallStart = (e: MessageEvent) => {
        try {
          const parsed = JSON.parse(e.data);
          const data = parsed.data || parsed;
          addLog({
            timestamp: parsed.timestamp || new Date().toISOString(),
            agent_name: data.agent_name || parsed.agent || 'Agent',
            type: 'tool_start',
            tool_name: data.tool_name || '',
            tool_params: data.parameters || {},
          });
        } catch {}
      };

      const onToolCallEnd = (e: MessageEvent) => {
        try {
          const parsed = JSON.parse(e.data);
          const data = parsed.data || parsed;
          addLog({
            timestamp: parsed.timestamp || new Date().toISOString(),
            agent_name: data.agent_name || parsed.agent || 'Agent',
            type: 'tool_end',
            tool_name: data.tool_name || '',
            tool_result: data.result || '',
            tool_success: data.success !== false,
          });
        } catch {}
      };

      const onDispatch = (e: MessageEvent) => {
        try {
          const parsed = JSON.parse(e.data);
          const data = parsed.data || parsed;
          addLog({
            timestamp: parsed.timestamp || new Date().toISOString(),
            agent_name: data.from_agent || parsed.agent || 'CEO Agent',
            type: 'dispatch',
            dispatch_to: data.to_agent || '',
            dispatch_task: data.task_description || '',
          });
        } catch {}
      };

      const onContent = (e: MessageEvent) => {
        try {
          const parsed = JSON.parse(e.data);
          const data = parsed.data || parsed;
          addLog({
            timestamp: parsed.timestamp || new Date().toISOString(),
            agent_name: data.agent_name || parsed.agent || 'Agent',
            type: 'content',
            content: data.content || '',
            phase: data.phase || '',
          });
        } catch {}
      };

      const onProgress = (e: MessageEvent) => {
        try {
          const parsed = JSON.parse(e.data);
          const data = parsed.data || parsed;
          addLog({
            timestamp: parsed.timestamp || new Date().toISOString(),
            agent_name: data.agent_name || parsed.agent || 'Workflow Engine',
            type: 'progress',
            message: data.message || parsed.message || `阶段 ${data.state} ${data.progress}%`,
            phase: data.state || '',
          });
        } catch {}
      };

      const onDone = () => {
        closed = true;
        clearEventSource();
      };

      es.addEventListener('agent.thinking', onThinking);
      es.addEventListener('agent.tool_call_start', onToolCallStart);
      es.addEventListener('agent.tool_call_end', onToolCallEnd);
      es.addEventListener('agent.dispatch', onDispatch);
      es.addEventListener('agent.content', onContent);
      es.addEventListener('workflow.progress_updated', onProgress);
      es.addEventListener('done', onDone);

      es.onerror = () => {
        if (closed) return;
        retryCount++;
        if (retryCount > SSE_MAX_RETRIES) {
          clearEventSource();
          return;
        }
        const delay = Math.min(SSE_INITIAL_DELAY * Math.pow(2, retryCount - 1), SSE_MAX_DELAY);
        clearEventSource();
        // 重连前清空日志，避免后端重放事件导致重复
        setAgentLogs([]);
        retryTimer = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      clearEventSource();
    };
  }, [taskId]);

  const currentState = getWorkflowState(workflow);
  const currentStepIndex = useMemo(() => {
    if (!workflow) return -1;
    
    // 如果工作流已终止（失败/取消/完成），根据 phase_history 确定实际完成的步骤
    if (terminalStates.has(workflow.current_state)) {
      // 找到最后一个成功完成的阶段（允许所有可能的 phase 值）
      const phaseChecks: Array<{ state: WorkflowState; phases: string[] }> = [
        { state: 'initial', phases: ['brainstorming', 'brainstorm'] },
        { state: 'requirement', phases: ['requirement', 'requirement_analysis'] },
        { state: 'retrieval', phases: ['retrieval', 'retrieval_analysis'] },
        { state: 'writing', phases: ['writing', 'patent_writing'] },
        { state: 'reviewing', phases: ['review', 'reviewing', 'quality_review', 'iteration'] },
      ];
      
      // 从后往前找最后一个完成的阶段
      for (let i = phaseChecks.length - 1; i >= 0; i--) {
        const { state, phases } = phaseChecks[i];
        const phaseResult = workflow.phase_history.find(p => phases.includes(p.phase) && p.success);
        if (phaseResult) {
          // 找到该 state 在 workflowSteps 中的索引
          const stepIndex = workflowSteps.findIndex((step) => step.state === state);
          if (stepIndex !== -1) {
            return stepIndex;
          }
        }
      }
      return -1;
    }
    
    // 正常运行中的工作流，使用原来的逻辑
    return workflowSteps.findIndex((step) => step.state === currentState);
  }, [currentState, workflow]);
  const agents = useMemo(() => createAgents(currentState, workflow), [currentState, workflow]);
  const historyLogs = useMemo(() => (taskId ? createHistoryLogs(workflow, taskId) : []), [workflow, taskId]);
  // SSE事件优先；如果有实时事件则只用SSE数据（更详细），否则用历史回放
  const allLogs = useMemo(
    () => (agentLogs.length > 0 ? agentLogs : historyLogs),
    [historyLogs, agentLogs]
  );
  const isInitialized = workflow?.current_state === 'initialized';
  const isTerminal = workflow ? terminalStates.has(workflow.current_state) : false;
  const isRunning = Boolean(workflow && !isInitialized && !isTerminal);
  const canRestart = Boolean(workflow && workflow.current_state !== 'completed');

  const loadWorkflow = useCallback(async (showLoading = false) => {
    if (!taskId) {
      setError('缺少任务 ID');
      setIsLoading(false);
      setIsRefreshing(false);
      return;
    }

    if (showLoading) {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    try {
      const data = await workflowApi.get(taskId);
      setWorkflow(data);
      setError(null);
      setPollIntervalMs(3000);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '获取工作流状态失败');
      setPollIntervalMs((currentInterval) => Math.min(currentInterval * 2, 30000));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [taskId]);

  useEffect(() => {
    if (!taskId) return;

    loadWorkflow(true).catch((requestError) => {
      setError(requestError instanceof Error ? requestError.message : '获取工作流状态失败');
    });
  }, [loadWorkflow, taskId]);

  useEffect(() => {
    if (!taskId || isTerminal) return;

    const timer = window.setInterval(() => {
      loadWorkflow(false).catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '获取工作流状态失败');
      });
    }, pollIntervalMs);

    return () => window.clearInterval(timer);
  }, [isTerminal, loadWorkflow, pollIntervalMs, taskId]);

  const getStatusBadge = (status: AgentInfo['status']) => {
    switch (status) {
      case 'working':
        return <Badge variant="green-soft">进行中</Badge>;
      case 'completed':
        return <Badge variant="green">已完成</Badge>;
      case 'error':
        return <Badge variant="orange">错误</Badge>;
      default:
        return <Badge variant="gray">等待中</Badge>;
    }
  };

  if (!taskId) {
    return (
      <div className="py-section-lg bg-surface min-h-screen">
        <div className="container mx-auto px-md">
          <Card className="border-red-200 bg-red-50">
            <CardContent className="pt-lg">
              <div className="flex items-center gap-2 text-red-700">
                <AlertCircle className="w-5 h-5" />
                <span className="text-body-sm-medium">缺少任务 ID，无法加载工作流详情。</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  const renderAgentOutput = (
    type: 'requirement' | 'retrieval' | 'draft' | 'review',
    output: Record<string, unknown> | undefined,
    icon: typeof Brain,
    emptyMessage: string
  ) => {
    if (!hasOutput(output)) {
      return <EmptyOutput icon={icon} message={emptyMessage} />;
    }

    // Check for multi-round outputs in phase_history
    const getPhaseOutputs = (phaseName: string): Record<string, unknown>[] => {
      if (!workflow) return [];
      const outputs = workflow.phase_history
        .filter((p) => p.phase === phaseName && p.success)
        .map((p) => p.output as Record<string, unknown>)
        .filter((o) => o && Object.keys(o).length > 0);
      // If no outputs from history, use the current output
      return outputs.length > 0 ? outputs : (output ? [output] : []);
    };

    switch (type) {
      case 'requirement':
        return <RequirementAnalysisView data={output!} />;
      case 'retrieval':
        return <RetrievalReportView data={output!} />;
      case 'draft': {
        const draftRounds = getPhaseOutputs('writing');
        if (draftRounds.length > 1) {
          return (
            <MultiRoundView
              rounds={draftRounds}
              label="撰写"
              renderRound={(data) => <PatentDraftView data={data} taskId={taskId} title={workflow?.title} />}
            />
          );
        }
        return <PatentDraftView data={output!} taskId={taskId} title={workflow?.title} />;
      }
      case 'review': {
        const reviewRounds = getPhaseOutputs('review');
        if (reviewRounds.length > 1) {
          return (
            <MultiRoundView
              rounds={reviewRounds}
              label="审查"
              renderRound={(data, idx) => <QualityReviewView data={data} roundIndex={idx} />}
            />
          );
        }
        return <QualityReviewView data={output!} />;
      }
      default:
        return (
          <CodeBlock language="json">
            {JSON.stringify(output, null, 2)}
          </CodeBlock>
        );
    }
  };

  return (
    <div className="py-section-lg bg-surface min-h-screen">
      <div className="container mx-auto px-md">
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-md mb-xl">
          <div>
            <h1 className="text-heading-3 font-euclid font-medium text-ink mb-xs">
              {workflow?.title || '专利申请流程'}
            </h1>
            <p className="text-body-sm text-steel">
              任务 ID: {taskId}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Badge 
              variant={
                error ? 'orange' :
                workflow?.current_state === 'failed' ? 'red-soft' :
                workflow?.current_state === 'cancelled' ? 'orange' :
                workflow?.current_state === 'awaiting_user_decision' ? 'soft' :
                workflow?.current_state === 'completed' ? 'green-soft' :
                'green-soft'
              } 
              color={workflow?.current_state === 'awaiting_user_decision' ? 'purple' : undefined}
              className="text-sm"
            >
              {error ? '获取失败' : getStatusLabel(workflow)}
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                loadWorkflow(false).catch((requestError) => {
                  setError(requestError instanceof Error ? requestError.message : '获取工作流状态失败');
                });
              }}
              disabled={isRefreshing}
            >
              <RefreshCw className={`w-4 h-4 mr-1 ${isRefreshing ? 'animate-spin' : ''}`} />
              刷新
            </Button>
            {isInitialized && (
              <Button
                variant="ghost"
                size="sm"
                onClick={async () => {
                  try {
                    await workflowApi.start(taskId);
                    setAgentLogs([]);
                    loadWorkflow(true);
                  } catch (requestError) {
                    setError(requestError instanceof Error ? requestError.message : '启动工作流失败');
                  }
                }}
              >
                <Play className="w-4 h-4 mr-1" />
                开始处理
              </Button>
            )}
            {isRunning && (
              <Button
                variant="ghost"
                size="sm"
                onClick={async () => {
                  try {
                    if (isPaused) {
                      await workflowApi.unpause(taskId);
                      setIsPaused(false);
                    } else {
                      await workflowApi.pause(taskId);
                      setIsPaused(true);
                    }
                  } catch (requestError) {
                    setError(requestError instanceof Error ? requestError.message : '更新工作流状态失败');
                  }
                }}
              >
                {isPaused ? <Play className="w-4 h-4 mr-1" /> : <Pause className="w-4 h-4 mr-1" />}
                {isPaused ? '恢复' : '暂停'}
              </Button>
            )}
            {canRestart && (
              <Button
                variant="ghost"
                size="sm"
                onClick={async () => {
                  try {
                    await workflowApi.restart(taskId);
                    setAgentLogs([]);
                    loadWorkflow(true);
                  } catch (requestError) {
                    setError(requestError instanceof Error ? requestError.message : '重新开始工作流失败');
                  }
                }}
              >
                <RefreshCw className="w-4 h-4 mr-1" />
                重新开始
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                // 跳转到关联的对话页面（通过 workflow 的 conversation_id）
                const convId = workflow?.conversation_id;
                if (convId) {
                  router.push(`/chat?conv_id=${encodeURIComponent(convId)}`);
                } else {
                  router.push('/chat');
                }
              }}
            >
              <MessageSquare className="w-4 h-4 mr-1" />
              前往对话补充
            </Button>
            {isTerminal && workflow?.current_state === 'completed' && (
              <Button
                variant="default"
                size="sm"
                onClick={() => {
                  const link = document.createElement('a');
                  link.href = workflowApi.exportDocx(taskId);
                  link.download = `${workflow?.title || '专利申请文件'}.docx`;
                  document.body.appendChild(link);
                  link.click();
                  document.body.removeChild(link);
                }}
              >
                <Download className="w-4 h-4 mr-1" />
                下载专利文件
              </Button>
            )}
          </div>
        </div>

        {error && (
          <Card className="mb-xl border-red-200 bg-red-50">
            <CardContent className="pt-lg">
              <div className="flex items-center gap-2 text-red-700">
                <AlertCircle className="w-5 h-5" />
                <span className="text-body-sm-medium">{error}</span>
              </div>
            </CardContent>
          </Card>
        )}

        {workflow?.current_state === 'awaiting_user_decision' && (
          <Card className="mb-xl border-purple-200 bg-purple-50" data-testid="quality-remediation-card">
            <CardContent className="pt-lg space-y-md">
              <div>
                <h2 className="text-body-md-medium font-medium text-purple-900">质量未达标，等待补充信息</h2>
                <p className="text-body-sm text-purple-800 mt-xs">
                  当前流程没有失败，但还缺少继续自动修复所需的信息。你可以直接继续自动修复，或先补充信息再继续。
                </p>
              </div>
              {Array.isArray(workflow.quality_remediation?.missing_information) && workflow.quality_remediation.missing_information.length > 0 && (
                <div>
                  <p className="text-body-sm-medium text-purple-900 mb-xs">建议补充：</p>
                  <ul className="list-disc pl-5 text-body-sm text-purple-800 space-y-1">
                    {workflow.quality_remediation.missing_information.map((item, idx) => (
                      <li key={`${item}-${idx}`}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
              <Textarea
                value={supplementalInfo}
                onChange={(event) => setSupplementalInfo(event.target.value)}
                placeholder="如果你已掌握缺失信息，可在这里补充后继续。"
              />
              <div className="flex flex-wrap gap-3">
                <Button
                  onClick={async () => {
                    try {
                      setDecisionPending(true);
                      await workflowApi.decision(taskId, 'continue_auto_fix');
                      setSupplementalInfo('');
                      loadWorkflow(false);
                    } catch (requestError) {
                      setError(requestError instanceof Error ? requestError.message : '继续自动修复失败');
                    } finally {
                      setDecisionPending(false);
                    }
                  }}
                  disabled={decisionPending}
                >
                  继续自动修复
                </Button>
                <Button
                  variant="secondary"
                  onClick={async () => {
                    try {
                      setDecisionPending(true);
                      await workflowApi.decision(taskId, 'provide_info', supplementalInfo.trim());
                      setSupplementalInfo('');
                      loadWorkflow(false);
                    } catch (requestError) {
                      setError(requestError instanceof Error ? requestError.message : '补充信息后继续失败');
                    } finally {
                      setDecisionPending(false);
                    }
                  }}
                  disabled={decisionPending || !supplementalInfo.trim()}
                >
                  补充信息后继续
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Progress Stepper */}
        <Card className="mb-xl">
          <CardContent className="pt-xl">
            <div className="flex items-center justify-between overflow-x-auto pb-md">
              {workflowSteps.map((step, index) => {
                const Icon = step.icon;
                const isCompleted = index < currentStepIndex || currentState === 'completed';
                const isCurrent = index === currentStepIndex && currentState !== 'completed';

                return (
                  <div key={step.state} className="flex items-center">
                    <div className="flex flex-col items-center min-w-[100px]">
                      <div
                        className={`w-10 h-10 rounded-full flex items-center justify-center transition-all ${
                          isCompleted
                            ? 'bg-brand-green text-ink'
                            : isCurrent
                            ? 'bg-brand-green-soft text-brand-green-dark ring-4 ring-brand-green/20'
                            : 'bg-hairline-soft text-muted'
                        }`}
                      >
                        <Icon className="w-5 h-5" />
                      </div>
                      <span
                        className={`mt-xs text-caption font-medium whitespace-nowrap ${
                          isCompleted || isCurrent ? 'text-ink' : 'text-muted'
                        }`}
                      >
                        {step.label}
                      </span>
                    </div>
                    {index < workflowSteps.length - 1 && (
                      <ChevronRight
                        className={`w-5 h-5 mx-sm ${
                          isCompleted ? 'text-brand-green' : 'text-hairline-strong'
                        }`}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {isLoading ? (
          <Card>
            <CardContent className="py-xxl text-center text-muted">
              <RefreshCw className="w-8 h-8 mx-auto mb-md animate-spin" />
              <p>正在加载工作流状态...</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid lg:grid-cols-3 gap-xl">
            {/* Agent Status Cards */}
            <div className="lg:col-span-1 space-y-md">
              <h2 className="text-heading-5 font-euclid font-medium text-ink mb-md">
                Agent 工作状态
              </h2>
              {agents.map((agent) => (
                <Card key={agent.id} hoverable>
                  <CardContent className="pt-lg">
                    <div className="flex items-start justify-between gap-md">
                      <div className="flex items-center gap-md">
                        <span className="text-2xl">{agent.icon}</span>
                        <div>
                          <h3 className="text-body-md-medium font-medium text-ink">
                            {agent.name}
                          </h3>
                          <p className="text-caption text-steel">{agent.role}</p>
                        </div>
                      </div>
                      {getStatusBadge(agent.status)}
                    </div>
                    <p className="mt-md text-body-sm text-steel">
                      {agent.description}
                    </p>
                    {agent.id !== 'ceo' && (agent.status === 'completed' || agent.status === 'error') && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="mt-md w-full"
                        onClick={async () => {
                          const phaseMap: Record<string, string> = {
                            requirement: 'requirement_analysis',
                            retrieval: 'retrieval_analysis',
                            writing: 'patent_writing',
                            review: 'quality_review',
                          };
                          const phase = phaseMap[agent.id];
                          if (phase) {
                            try {
                              await workflowApi.retryPhase(taskId, phase);
                              loadWorkflow(false);
                            } catch {}
                          }
                        }}
                      >
                        <RefreshCw className="w-3.5 h-3.5 mr-1" />
                        重试该阶段
                      </Button>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Main Content - Event Log and Data Preview */}
            <div className="lg:col-span-2 space-y-xl">
              {/* Event Log - Agent Terminal */}
              <Card>
                <CardHeader>
                  <CardTitle>实时工作日志</CardTitle>
                  <CardDescription>
                    各 Agent 的思考过程、工具调用和输出记录
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <AgentTerminalLog entries={allLogs} />
                </CardContent>
              </Card>

              {/* Data Preview Tabs */}
              <Card>
                <CardHeader>
                  <CardTitle>阶段输出预览</CardTitle>
                  <CardDescription>
                    查看各阶段生成的结构化数据和文档
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Tabs defaultValue="requirement">
                    <TabsList variant="pill" className="mb-lg">
                      <TabsTrigger value="requirement" variant="pill">
                        需求分析
                      </TabsTrigger>
                      <TabsTrigger value="retrieval" variant="pill" disabled={currentStepIndex < 2}>
                        检索报告
                      </TabsTrigger>
                      <TabsTrigger value="draft" variant="pill" disabled={currentStepIndex < 3}>
                        申请文件
                      </TabsTrigger>
                      <TabsTrigger value="review" variant="pill" disabled={currentStepIndex < 4}>
                        审查意见
                      </TabsTrigger>
                    </TabsList>

                    <TabsContent value="requirement">
                      {renderAgentOutput(
                        'requirement',
                        workflow?.outputs.requirement_analysis,
                        Brain,
                        '需求分析尚未完成，请稍候...'
                      )}
                    </TabsContent>

                    <TabsContent value="retrieval">
                      {renderAgentOutput(
                        'retrieval',
                        workflow?.outputs.retrieval_report,
                        Search,
                        '检索分析进行中，请稍候...'
                      )}
                    </TabsContent>

                    <TabsContent value="draft">
                      {renderAgentOutput(
                        'draft',
                        workflow?.outputs.patent_draft,
                        FileEdit,
                        '等待检索完成后开始撰写...'
                      )}
                    </TabsContent>

                    <TabsContent value="review">
                      {renderAgentOutput(
                        'review',
                        workflow?.outputs.review_report,
                        CheckSquare,
                        '等待文件撰写完成后开始审查...'
                      )}
                    </TabsContent>
                  </Tabs>
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
