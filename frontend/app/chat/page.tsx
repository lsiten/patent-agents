'use client';

import { Suspense, useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Send, Bot, User, Sparkles, FileText, Loader2, Plus, Trash2,
  MessageSquare, ChevronRight, AlertCircle, CheckCircle2, Paperclip, X, Copy, Search,
  ChevronDown, PauseCircle, PlayCircle
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/Toast';
import { ToolCallCard } from '@/components/chat/ToolCallCard';
import { AgentActivityLog } from '@/components/chat/AgentActivityLog';
import { type DispatchActivity } from '@/components/chat/DispatchPanel';
import { WorkflowProgressStrip } from '@/components/chat/WorkflowProgressStrip';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { clsx } from 'clsx';
import { conversationApi, workflowApi } from '@/lib/api';
import type { ConversationSummary } from '@/lib/api';
import type { AgentEvent, AgentWorkEvent, ChatMessage } from '@/types';

const terminalWorkflowStates = new Set(['completed', 'failed', 'cancelled']);

function upsertMessage(messages: ChatMessage[], nextMessage: ChatMessage): ChatMessage[] {
  if (messages.some((message) => message.id === nextMessage.id)) return messages;
  return [...messages, nextMessage];
}

function updateDispatchActivities(activities: DispatchActivity[], event: AgentWorkEvent): DispatchActivity[] {
  const task = typeof event.data?.task === 'string' ? event.data.task : event.action;

  if (event.event_type === 'agent.work.started') {
    if (activities.some((activity) => activity.agentId === event.agent_id && activity.task === task && activity.status === 'running')) {
      return activities;
    }
    return [...activities, {
      id: `workflow-${event.timestamp}-${event.agent_id}`,
      agentId: event.agent_id,
      agentName: event.agent_name,
      task,
      status: 'running',
      startedAt: event.timestamp,
    }];
  }

  if (event.event_type === 'agent.work.completed' || event.event_type === 'agent.work.failed') {
    const nextStatus = event.event_type === 'agent.work.completed' ? 'completed' : 'failed';
    const idx = activities.findLastIndex((activity) => activity.agentId === event.agent_id && activity.task === task && activity.status === 'running');
    if (idx === -1) {
      return [...activities, {
        id: `workflow-${event.timestamp}-${event.agent_id}`,
        agentId: event.agent_id,
        agentName: event.agent_name,
        task,
        status: nextStatus,
        result: event.summary || event.error,
        startedAt: event.timestamp,
        completedAt: event.timestamp,
      }];
    }
    const updated = [...activities];
    updated[idx] = { ...updated[idx], status: nextStatus, result: event.summary || event.error, completedAt: event.timestamp };
    return updated;
  }

  return activities;
}

function updateWorkflowActivityMessage(
  messages: ChatMessage[],
  workflowTaskId: string,
  event: AgentEvent,
): ChatMessage[] {
  const liveId = `workflow-live-${workflowTaskId}`;
  const existingIndex = messages.findIndex((message) => message.id === liveId);
  const existing = existingIndex >= 0 ? messages[existingIndex] : null;
  const agentEvents = [...(existing?.agent_events || []), event].slice(-120);
  const toolCalls = [...(existing?.tool_calls || [])];

  if (event.type === 'tool_call_start') {
    const toolName = typeof event.data?.name === 'string' ? event.data.name : 'unknown';
    const parameters = typeof event.data?.parameters === 'object' && event.data.parameters !== null && !Array.isArray(event.data.parameters)
      ? event.data.parameters as Record<string, unknown>
      : {};
    toolCalls.push({
      name: toolName,
      parameters,
      result: null,
      success: true,
    });
  }

  if (event.type === 'tool_call_end') {
    const toolName = typeof event.data?.name === 'string' ? event.data.name : 'unknown';
    const idx = toolCalls.findLastIndex((tool) => tool.name === toolName && tool.result === null);
    const result = event.data?.result ?? '';
    const success = typeof event.data?.success === 'boolean' ? event.data.success : true;
    const nextTool = {
      name: toolName,
      parameters: idx >= 0 ? toolCalls[idx].parameters : {},
      result,
      success,
      error: success ? undefined : String(event.data?.error || result || '工具执行失败'),
    };
    if (idx >= 0) {
      toolCalls[idx] = nextTool;
    } else {
      toolCalls.push(nextTool);
    }
  }

  const nextMessage: ChatMessage = {
    id: liveId,
    role: 'agent',
    agent_name: 'workflow_engine',
    content: '工作流实时过程',
    timestamp: event.timestamp || new Date().toISOString(),
    type: 'progress',
    metadata: { workflow_id: workflowTaskId, live_activity: true },
    agent_events: agentEvents,
    tool_calls: toolCalls.length > 0 ? toolCalls : undefined,
  };

  if (existingIndex < 0) {
    return [...messages, nextMessage];
  }

  const updated = [...messages];
  updated[existingIndex] = { ...existing!, ...nextMessage };
  return updated;
}

function createWelcomeMessage(): ChatMessage {
  return {
    id: 'welcome',
    role: 'assistant',
    content: `您好！我是专利智脑的专利代理人助理。请描述您的发明创造，我们将一起完善技术方案。

例如：
• 这是哪个技术领域的创新？
• 它解决了什么具体问题？
• 核心技术方案大概是什么？

多轮对话后，我可以帮您启动正式的专利申请流程。`,
    timestamp: new Date().toISOString(),
  };
}

function createLocalChatMessage(
  role: ChatMessage['role'],
  content: string,
  options?: Pick<ChatMessage, 'type' | 'metadata'>,
): ChatMessage {
  return {
    id: `local-${Date.now()}-${crypto.randomUUID()}`,
    role,
    content,
    timestamp: new Date().toISOString(),
    ...options,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function stringField(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === 'string' && value.trim() ? value : null;
}

function resolveAgentName(data: unknown, fallback = 'patent.ceo.v1'): string {
  if (!isRecord(data)) return fallback;

  const direct = stringField(data, 'agent_name')
    ?? stringField(data, 'agent')
    ?? stringField(data, 'profile_id');
  if (direct) return direct;

  const result = data.result;
  if (isRecord(result)) {
    const resultAgent = stringField(result, 'agent')
      ?? stringField(result, 'agent_name')
      ?? stringField(result, 'profile_id');
    if (resultAgent) return resultAgent;
  }

  const parameters = data.parameters;
  if (isRecord(parameters)) {
    const parameterAgent = stringField(parameters, 'agent')
      ?? stringField(parameters, 'agent_name')
      ?? stringField(parameters, 'agent_id');
    if (parameterAgent) return parameterAgent;
  }

  return fallback;
}

function shouldAutoStartWorkflowFromPrompt(content: string): boolean {
  const normalized = content.replace(/\s+/g, '').toLowerCase();
  const requestsCompletePatentApplication = /生成完整(?:发明)?专利申请文件/.test(normalized)
    || /完整(?:发明)?专利申请(?:文件|流程)/.test(normalized);
  const requestsFullProcess = normalized.includes('全流程')
    || normalized.includes('完整流程')
    || normalized.includes('工作流');

  return requestsCompletePatentApplication && requestsFullProcess;
}

function conversationWorkflowState(conversation: ConversationSummary): string {
  return conversation.workflow_state ?? conversation.status;
}

function workflowStatusDisplay(state: string): { label: string; tone: 'done' | 'failed' | 'waiting' | 'running' | 'initial' } {
  if (state === 'completed') return { label: '已完成', tone: 'done' };
  if (state === 'failed') return { label: '已失败', tone: 'failed' };
  if (state === 'cancelled') return { label: '已取消', tone: 'failed' };
  if (state === 'awaiting_user_decision') return { label: '待处理', tone: 'waiting' };
  if (state === 'initial' || state === 'initialized' || state === 'created') return { label: '待启动', tone: 'initial' };
  return { label: '进行中', tone: 'running' };
}

function WorkflowStatusIcon({ tone }: { tone: ReturnType<typeof workflowStatusDisplay>['tone'] }) {
  if (tone === 'done') return <CheckCircle2 className="w-3 h-3 text-green-600" />;
  if (tone === 'failed') return <AlertCircle className="w-3 h-3 text-red-500" />;
  if (tone === 'waiting') return <PauseCircle className="w-3 h-3 text-purple-600" />;
  if (tone === 'initial') return <PlayCircle className="w-3 h-3 text-slate-500" />;
  return <Loader2 className="w-3 h-3 text-amber-500 animate-spin" />;
}

interface ParsedMessageContent {
  conclusion: string;
  interaction: string;
}

function parseMessageContent(content: string): ParsedMessageContent {
  const lines = content.split('\n');
  const interactionLines: string[] = [];
  const conclusionLines: string[] = [];
  
  for (const line of lines) {
    if (line.trim().startsWith('[ASSISTANT:]') || line.trim().startsWith('[USER:]')) {
      interactionLines.push(line);
    } else {
      conclusionLines.push(line);
    }
  }
  
  return {
    conclusion: conclusionLines.join('\n').trim(),
    interaction: interactionLines.join('\n').trim(),
  };
}

interface InteractionPanelProps {
  interaction: string;
}

function InteractionPanel({ interaction }: InteractionPanelProps) {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <div className="mt-2 rounded-xl border border-hairline bg-surface/70">
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
        <span className="text-xs font-medium text-slate">查看交互过程</span>
      </button>
      
      {expanded && (
        <div className="border-t border-hairline px-3 pb-3">
          <pre className="text-xs text-slate/80 whitespace-pre-wrap bg-canvas rounded-lg p-3 mt-2 max-h-64 overflow-y-auto">
            {interaction}
          </pre>
        </div>
      )}
    </div>
  );
}

function ChatPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const convIdFromParam = searchParams?.get('conv_id') ?? null;
  const taskIdFromParam = searchParams?.get('task_id') ?? null;

  // Conversation list
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loadingList, setLoadingList] = useState(true);

  // Active conversation
  const [activeConvId, setActiveConvId] = useState<string | null>(convIdFromParam);
  const [messages, setMessages] = useState<ChatMessage[]>([createWelcomeMessage()]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingConv, setIsLoadingConv] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'idle' | 'connecting' | 'connected' | 'disconnected'>('idle');
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [, setError] = useState<string | null>(null);
  const [showSidebar, setShowSidebar] = useState(true);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState(false);
  const [editTitleValue, setEditTitleValue] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Workflow state
  const [workflowTaskId, setWorkflowTaskId] = useState<string | null>(null);
  const [workflowState, setWorkflowState] = useState<string | null>(null);
  const [isStartingWorkflow, setIsStartingWorkflow] = useState(false);

  // Recommendations from backend
  const [recommendStartWorkflow, setRecommendStartWorkflow] = useState(false);
  const [suggestedTitle, setSuggestedTitle] = useState<string | null>(null);

  // Dispatch activities (CEO → specialist calls)
  const [dispatchActivities, setDispatchActivities] = useState<DispatchActivity[]>([]);

  // Pending confirmation from agent
  const [pendingConfirmation, setPendingConfirmation] = useState<{
    question: string;
    options: string[];
    convId: string;
  } | null>(null);

  const { addToast } = useToast();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sendingRef = useRef(false);
  const skipNextConversationLoadRef = useRef<string | null>(null);
  const conversationLoadSeqRef = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const filteredMessages = useMemo(() => {
    if (!searchQuery.trim()) return messages;
    const q = searchQuery.toLowerCase();
    return messages.filter(
      (m) => m.content && m.content.toLowerCase().includes(q)
    );
  }, [messages, searchQuery]);
  const visibleWorkflowTaskId = activeConvId ? workflowTaskId : null;
  const visibleWorkflowState = activeConvId ? workflowState : null;

  const appendSystemMessage = useCallback(
    (content: string, tone: 'info' | 'error' = 'info') => {
      setMessages((prev) => [
        ...prev,
        createLocalChatMessage('system', content, { metadata: { tone } }),
      ]);
    },
    []
  );

  const appendFileMessage = useCallback(
    (content: string, metadata: Record<string, unknown>) => {
      setMessages((prev) => [
        ...prev,
        createLocalChatMessage('user', content, { type: 'file', metadata }),
      ]);
    },
    []
  );

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleCopy = async (msgId: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(msgId);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      addToast({ type: 'error', title: '复制失败', message: '无法访问剪贴板' });
    }
  };

  const handleStartEditingTitle = () => {
    const currentTitle = conversations.find((c) => c.id === activeConvId)?.title || '';
    setEditTitleValue(currentTitle);
    setEditingTitle(true);
  };

  const handleSaveTitle = async () => {
    if (!activeConvId || !editTitleValue.trim()) {
      setEditingTitle(false);
      return;
    }
    try {
      const result = await conversationApi.rename(activeConvId, editTitleValue.trim());
      setConversations((prev) =>
        prev.map((c) => (c.id === activeConvId ? { ...c, title: result.title } : c))
      );
    } catch {
      addToast({ type: 'error', title: '重命名失败', message: '请稍后重试' });
    }
    setEditingTitle(false);
  };

  const handleKeyDownTitle = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSaveTitle();
    }
    if (e.key === 'Escape') {
      setEditingTitle(false);
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    // Small delay to let the UI settle after state changes  (existing)
    const timer = setTimeout(() => {
      inputRef.current?.focus();
    }, 50);
    return () => clearTimeout(timer);
  }, [messages.length, activeConvId, isLoading]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        handleNewConversation();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Load conversation list
  const loadConversations = useCallback(async () => {
    setLoadingList(true);
    try {
      const result = await conversationApi.list();
      setConversations(result.conversations);
    } catch {
      addToast({ type: 'error', title: '加载对话列表失败', message: '无法获取对话列表，请检查网络连接' });
    } finally {
      setLoadingList(false);
    }
  }, []);

  // Load conversation detail
  const loadConversation = useCallback(async (convId: string) => {
    const loadSeq = conversationLoadSeqRef.current + 1;
    conversationLoadSeqRef.current = loadSeq;
    setIsLoadingConv(true);
    setError(null);
    try {
      const detail = await conversationApi.get(convId);
      if (conversationLoadSeqRef.current !== loadSeq) return;
      setMessages(detail.messages.length > 0 ? detail.messages : [createWelcomeMessage()]);
      setWorkflowTaskId(detail.linked_workflow_id ?? null);
      setWorkflowState(detail.status ?? null);
      if (detail.linked_workflow_id) {
        setPendingConfirmation(null);
        setRecommendStartWorkflow(false);
      }

      if (detail.linked_workflow_id) {
        try {
          const workflow = await workflowApi.get(detail.linked_workflow_id);
          if (conversationLoadSeqRef.current === loadSeq) {
            setWorkflowState(workflow.current_state);
          }
        } catch {
        }
      }
    } catch (err) {
      if (conversationLoadSeqRef.current !== loadSeq) return;
      setError(err instanceof Error ? err.message : '加载对话失败');
      setMessages([createWelcomeMessage()]);
    } finally {
      if (conversationLoadSeqRef.current === loadSeq) {
        setIsLoadingConv(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadConversations();
    const interval = setInterval(() => { void loadConversations(); }, 30000);
    return () => clearInterval(interval);
  }, [loadConversations]);

  useEffect(() => {
    if (convIdFromParam) {
      setActiveConvId(convIdFromParam);
      setConnectionStatus('idle');
      setIsLoading(false);

      if (skipNextConversationLoadRef.current === convIdFromParam) {
        skipNextConversationLoadRef.current = null;
        return;
      }

      void loadConversation(convIdFromParam);
      return;
    }

    skipNextConversationLoadRef.current = null;
    conversationLoadSeqRef.current += 1;
    setActiveConvId(null);
    setConnectionStatus('idle');
    setIsLoading(false);
    setMessages([createWelcomeMessage()]);
    setIsLoadingConv(false);
    setWorkflowTaskId(null);
    setWorkflowState(null);
    setRecommendStartWorkflow(false);
    setSuggestedTitle(null);
    setPendingConfirmation(null);
    setDispatchActivities([]);
    setError(null);
  }, [convIdFromParam, loadConversation]);

  useEffect(() => {
    if (!taskIdFromParam || convIdFromParam) return;

    const linkedConversation = conversations.find((conversation) => (
      conversation.linked_workflow_id === taskIdFromParam
      || conversation.workflow_task_id === taskIdFromParam
    ));

    if (linkedConversation) {
      if (activeConvId === linkedConversation.id) return;

      setActiveConvId(linkedConversation.id);
      setConnectionStatus('idle');
      setIsLoading(false);
      setPendingConfirmation(null);
      setRecommendStartWorkflow(false);
      setDispatchActivities([]);
      setError(null);
      window.history.replaceState(null, '', `/chat?conv_id=${encodeURIComponent(linkedConversation.id)}`);
      void loadConversation(linkedConversation.id);
      return;
    }

    setWorkflowTaskId(taskIdFromParam);
    setWorkflowState(null);

    workflowApi.get(taskIdFromParam).then((workflow) => {
      setWorkflowState(workflow.current_state);
    }).catch(() => {});
  }, [activeConvId, conversations, convIdFromParam, loadConversation, taskIdFromParam]);

  useEffect(() => {
    if (!activeConvId || !workflowTaskId || (workflowState && terminalWorkflowStates.has(workflowState))) return;

    const stream = conversationApi.eventStream(activeConvId, {
      onAgentWork: (event) => {
        setDispatchActivities((current) => updateDispatchActivities(current, event));
        if (event.event_type === 'agent.work.failed') {
          setWorkflowState('failed');
        }
      },
      onAgentActivity: (event) => {
        setMessages((current) => updateWorkflowActivityMessage(current, workflowTaskId, event));
      },
      onConversationMessage: (message) => {
        setMessages((current) => upsertMessage(current, message));
      },
      onDone: () => {
        void loadConversation(activeConvId);
      },
      onError: () => {},
    });

    return () => stream.abort();
  }, [activeConvId, loadConversation, workflowState, workflowTaskId]);

  useEffect(() => {
    if (!activeConvId || !workflowTaskId) return;

    let stopped = false;
    let interval: ReturnType<typeof setInterval> | null = null;

    const syncWorkflowState = async () => {
      try {
        const workflow = await workflowApi.get(workflowTaskId);
        if (stopped) return;
        setWorkflowState(workflow.current_state);
        setConversations((current) => current.map((conversation) => (
          conversation.id === activeConvId
          || conversation.linked_workflow_id === workflowTaskId
          || conversation.workflow_task_id === workflowTaskId
            ? { ...conversation, workflow_state: workflow.current_state }
            : conversation
        )));
        if (terminalWorkflowStates.has(workflow.current_state) && interval) {
          clearInterval(interval);
          interval = null;
        }
      } catch {
      }
    };

    void syncWorkflowState();
    interval = setInterval(syncWorkflowState, 3000);

    return () => {
      stopped = true;
      if (interval) clearInterval(interval);
    };
  }, [activeConvId, workflowTaskId]);

  // Create new conversation
  const handleNewConversation = async () => {
    conversationLoadSeqRef.current += 1;
    skipNextConversationLoadRef.current = null;
    setConnectionStatus('idle');
    setIsLoading(false);
    setActiveConvId(null);
    setMessages([createWelcomeMessage()]);
    setWorkflowTaskId(null);
    setWorkflowState(null);
    setRecommendStartWorkflow(false);
    setSuggestedTitle(null);
    setPendingConfirmation(null);
    setDispatchActivities([]);
    setError(null);
    setInput('');
    setPendingFile(null);
    window.history.replaceState(null, '', '/chat');
  };

  // Select conversation
  const handleSelectConversation = (convId: string) => {
    conversationLoadSeqRef.current += 1;
    setActiveConvId(convId);
    setConnectionStatus('idle');
    setIsLoading(false);
    setWorkflowTaskId(null);
    setWorkflowState(null);
    setRecommendStartWorkflow(false);
    setSuggestedTitle(null);
    setPendingConfirmation(null);
    setDispatchActivities([]);
    setError(null);
    setInput('');
    window.history.replaceState(null, '', `/chat?conv_id=${encodeURIComponent(convId)}`);
    setShowSidebar(false);
  };

  // Delete conversation
  const handleDeleteConversation = (e: React.MouseEvent, convId: string) => {
    e.stopPropagation();
    setDeleteConfirmId(convId);
  };

  const executeDeleteConversation = async () => {
    const convId = deleteConfirmId;
    if (!convId) return;
    setDeleteConfirmId(null);
    try {
      await conversationApi.delete(convId);
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      if (activeConvId === convId) {
        handleNewConversation();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  // Send message
  const handleSend = async (overrideContent?: string) => {
    let content = (overrideContent ?? input).trim();
    if ((!content && !pendingFile) || isLoading || isUploadingFile || sendingRef.current) return;
    // Clear pending confirmation on any send action
    setPendingConfirmation(null);
    sendingRef.current = true;

    let fileUpload: { messageId: string; metadata: Record<string, unknown>; convId: string } | null = null;
    let isAutoAnalysis = false;
    if (pendingFile) {
      try {
        // 如果用户有输入文字内容，传递 false 避免在 uploadPendingFile 中创建消息
        // 消息将在下方统一创建，包含文件信息和文字内容
        fileUpload = await uploadPendingFile(!content);
      } catch {
        sendingRef.current = false;
        return;
      }
    }

    if (!content) {
      // File-only upload: auto-trigger AI analysis instead of waiting for text input
      if (fileUpload) {
        content = '请分析我上传的技术交底文件，并开始专利申请讨论';
        isAutoAnalysis = true;
        appendSystemMessage('正在分析文件：AI 正在解读您上传的交底书...');
      } else {
        sendingRef.current = false;
        return;
      }
    }

    // Skip adding a user message for auto-analysis — the file upload already stored it
    if (isAutoAnalysis) {
      // The streaming assistant message will be added below; no duplicate user message needed
    } else {
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
        type: fileUpload ? 'file' : 'text',
        metadata: fileUpload?.metadata,
      };
      setMessages((prev) => [...prev, userMsg]);
    }
    setInput('');
    setIsLoading(true);
    setError(null);
    setConnectionStatus('connecting');

    try {
      let convId = activeConvId;

      // If activeConvId is stale after file upload (React closure doesn't update),
      // use the convId returned by uploadPendingFile instead
      if (!convId && fileUpload?.convId) {
        convId = fileUpload.convId;
        setActiveConvId(convId);
        skipNextConversationLoadRef.current = convId;
        window.history.replaceState(null, '', `/chat?conv_id=${encodeURIComponent(convId)}`);
        void loadConversations();
      }

      // If no active conversation, create one
      if (!convId) {
        const created = await conversationApi.create({
          user_id: 'default_user',
          title: content.slice(0, 80),
        });
        convId = created.id;
        setActiveConvId(convId);
        skipNextConversationLoadRef.current = convId;
        window.history.replaceState(null, '', `/chat?conv_id=${encodeURIComponent(convId)}`);
        void loadConversations();
      }

      if (fileUpload && shouldAutoStartWorkflowFromPrompt(content)) {
        setConnectionStatus('idle');
        setIsLoading(false);
        sendingRef.current = false;
        setRecommendStartWorkflow(false);
        await handleStartWorkflow(convId);
        return;
      }

      // Create a streaming assistant message placeholder
      const streamMsgId = `assistant-stream-${Date.now()}`;
      let localEventSequence = 0;
      const nextLocalEventFields = (type: AgentEvent['type']) => ({
        id: `${streamMsgId}-${type}-${localEventSequence + 1}`,
        sequence: ++localEventSequence,
        call_id: streamMsgId,
      });
      const streamMsg: ChatMessage = {
        id: streamMsgId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        isStreaming: true,
        tool_calls: [],
        skill_uses: [],
        agent_events: [],
      };
      setMessages((prev) => [...prev, streamMsg]);
      let didAutoStartWorkflow = false;
      const maybeAutoStartWorkflow = () => {
        if (didAutoStartWorkflow || !shouldAutoStartWorkflowFromPrompt(content)) return;
        didAutoStartWorkflow = true;
        void handleStartWorkflow(convId);
      };

      // Use streaming API
      conversationApi.chatStream(convId, { content }, {
        onAgentActivity: (event: AgentEvent) => {
          setMessages((prev) => prev.map((m) =>
            m.id === streamMsgId
              ? {
                  ...m,
                  content: m.content || (event.type === 'thinking' ? event.message : m.content),
                  agent_events: [...(m.agent_events || []), event],
                }
              : m
          ));
        },
        onThinking: (_data) => {
          setMessages((prev) => {
            const now = new Date().toISOString();
            return prev.map((m) =>
              m.id === streamMsgId
                ? {
                    ...m,
                    content: m.content || '正在思考...',
                    agent_events: [
                      ...(m.agent_events || []),
                      {
                        ...nextLocalEventFields('thinking'),
                        type: 'thinking' as const,
                        agent_name: resolveAgentName(_data),
                        timestamp: now,
                        message: '思考中...',
                        data: _data as Record<string, unknown>,
                      },
                    ],
                  }
                : m
            );
          });
        },
        onSkillUse: (data) => {
          setMessages((prev) => {
            const now = new Date().toISOString();
            return prev.map((m) =>
              m.id === streamMsgId
                ? {
                    ...m,
                    skill_uses: [...(m.skill_uses || []), data],
                    agent_events: [
                      ...(m.agent_events || []),
                      {
                        ...nextLocalEventFields('skill_use'),
                        type: 'skill_use' as const,
                        agent_name: resolveAgentName(data),
                        timestamp: now,
                        message: `技能: ${data.name}`,
                        data: data as Record<string, unknown>,
                      },
                    ],
                  }
                : m
            );
          });
        },
        onToolCallStart: (data) => {
          setMessages((prev) => {
            const now = new Date().toISOString();
            return prev.map((m) =>
              m.id === streamMsgId
                ? {
                    ...m,
                    tool_calls: [...(m.tool_calls || []), { ...data, result: null, success: true }],
                    agent_events: [
                      ...(m.agent_events || []),
                      {
                        ...nextLocalEventFields('tool_call_start'),
                        type: 'tool_call_start' as const,
                        agent_name: resolveAgentName(data),
                        timestamp: now,
                        message: `调用工具: ${data.name}`,
                        data: data as Record<string, unknown>,
                      },
                    ],
                  }
                : m
            );
          });
          // Track dispatch_specialist calls in panel
          if (data.name === 'dispatch_specialist') {
            const params = data.parameters as Record<string, string>;
            const agentId = params.agent_id || 'unknown';
            const task = params.task || '';
            setDispatchActivities((prev) => [
              ...prev,
              {
                id: `dispatch-${Date.now()}-${agentId}`,
                agentId,
                agentName: agentId,
                task,
                status: 'running',
                startedAt: new Date().toISOString(),
              },
            ]);
          }
        },
        onToolCallEnd: (data) => {
          setMessages((prev) => {
            const now = new Date().toISOString();
            return prev.map((m) => {
              if (m.id !== streamMsgId) return m;
              const updatedCalls = (m.tool_calls || []).map((tc) =>
                tc.name === data.name && tc.result === null
                  ? { ...tc, result: data.result, success: data.success, error: data.error }
                  : tc
              );
              return {
                ...m,
                tool_calls: updatedCalls,
                agent_events: [
                  ...(m.agent_events || []),
                  {
                    ...nextLocalEventFields('tool_call_end'),
                    type: 'tool_call_end' as const,
                    agent_name: resolveAgentName(data),
                    timestamp: now,
                    message: `工具完成: ${data.name}`,
                    data: data as Record<string, unknown>,
                  },
                ],
              };
            });
          });
          // Update dispatch activity status
          if (data.name === 'dispatch_specialist') {
            setDispatchActivities((prev) => {
              const idx = prev.findLastIndex((a) => a.status === 'running');
              if (idx === -1) return prev;
              const updated = [...prev];
              const result = data.result as Record<string, unknown> | null;
              updated[idx] = {
                ...updated[idx],
                status: data.success ? 'completed' : 'failed',
                result: typeof result?.result === 'string' ? result.result.slice(0, 300) : JSON.stringify(result).slice(0, 300),
                completedAt: new Date().toISOString(),
              };
              return updated;
            });
          }
        },
        onStreamDelta: (data) => {
          setMessages((prev) => prev.map((m) =>
            m.id === streamMsgId
              ? { ...m, content: (m.content || '') + data.content, isStreaming: true }
              : m
          ));
        },
        onContent: (data) => {
          setMessages((prev) => prev.map((m) =>
            m.id === streamMsgId
              ? { ...m, content: data.content, isStreaming: true }
              : m
          ));
          if (data.has_recommendation) {
            setRecommendStartWorkflow(true);
            maybeAutoStartWorkflow();
          }
        },
        onConfirmation: (data) => {
          setPendingConfirmation({
            question: data.question,
            options: data.options,
            convId: convId as string,
          });
        },
        onStatus: (data) => {
          setMessages((prev) => {
            const now = new Date().toISOString();
            return prev.map((m) =>
              m.id === streamMsgId
                ? {
                    ...m,
                    agent_events: [
                      ...(m.agent_events || []),
                      {
                        ...nextLocalEventFields('status'),
                        type: 'status' as const,
                        agent_name: resolveAgentName(data),
                        timestamp: now,
                        message: data.message || data.status || '',
                        data: data as Record<string, unknown>,
                      },
                    ],
                  }
                : m
            );
          });
        },
        onDone: (data) => {
          setConnectionStatus('idle');
          // Replace streaming message with final persisted message
          setMessages((prev) => prev.map((m) =>
            m.id === streamMsgId
              ? { ...data.message, isStreaming: false }
              : m
          ));
          setIsLoading(false);
          sendingRef.current = false;
          if (data.has_recommendation || shouldAutoStartWorkflowFromPrompt(content)) {
            setRecommendStartWorkflow(true);
            maybeAutoStartWorkflow();
          }
          void loadConversations();
        },
        onError: (errorMsg) => {
          setConnectionStatus('idle');
          setMessages((prev) => [
            ...prev.filter((m) => m.id !== streamMsgId),
            createLocalChatMessage('system', `请求失败：${errorMsg}`, { metadata: { tone: 'error' } }),
          ]);
          setIsLoading(false);
          sendingRef.current = false;
        },
        onStatusChange: (status) => setConnectionStatus(status),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '发送消息失败';
      appendSystemMessage(`发送失败：${msg}`, 'error');
      sendingRef.current = false;
      setIsLoading(false);
    }
  };

  const handleConfirmationAnswer = async (answer: string) => {
    const currentConvId = pendingConfirmation?.convId;
    setPendingConfirmation(null);
    if (!currentConvId) return;
    await handleSend(answer);
  };

  const handleFileSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    const allowed = ['.txt', '.docx', '.pdf'];
    const lower = file.name.toLowerCase();
    if (!allowed.some((ext) => lower.endsWith(ext))) {
      appendSystemMessage('文件类型不支持：仅支持 .txt、.docx 和 .pdf 文件', 'error');
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      appendSystemMessage('文件过大：文件大小不能超过 10MB', 'error');
      return;
    }

    setPendingFile(file);
  };

  const uploadPendingFile = async (appendMessage = true): Promise<{
    messageId: string;
    metadata: Record<string, unknown>;
    charCount: number;
    convId: string;
  } | null> => {
    const file = pendingFile;
    if (!file) return null;

    setIsUploadingFile(true);
    setError(null);
    try {
      let convId = activeConvId;
      if (!convId) {
        const created = await conversationApi.create({
          user_id: 'default_user',
          title: file.name.slice(0, 80),
        });
        convId = created.id;
        setActiveConvId(convId);
        skipNextConversationLoadRef.current = convId;
        window.history.replaceState(null, '', `/chat?conv_id=${encodeURIComponent(convId)}`);
        void loadConversations();
      }

      const result = await conversationApi.uploadDisclosure(convId, file);

      // 仅当用户没有输入文字内容时才创建文件消息
      // 如果有文字内容，将由 handleSend 合并成一条消息
      if (appendMessage) {
        appendFileMessage(`文件已解析：${result.filename} · ${result.char_count} 字符`, {
          filename: result.filename,
          file_type: result.file_type,
          file_size: result.file_size,
          char_count: result.char_count,
          ...(result.metadata || {}),
        });
      }
      setPendingFile(null);
      return {
        messageId: result.message_id,
        metadata: {
          filename: result.filename,
          file_type: result.file_type,
          file_size: result.file_size,
          ...(result.metadata || {}),
        },
        charCount: result.char_count,
        convId,
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : '文件上传失败';
      appendSystemMessage(`上传失败：${message}`, 'error');
      throw err;
    } finally {
      setIsUploadingFile(false);
    }
  };

  // Start workflow from conversation
  const handleStartWorkflow = async (conversationId = activeConvId) => {
    if (!conversationId || isStartingWorkflow) return;
    setIsStartingWorkflow(true);
    setError(null);

    try {
      const result = await conversationApi.createWorkflow(conversationId);
      setWorkflowTaskId(result.task_id);
      setWorkflowState(result.status);
      setRecommendStartWorkflow(false);
      setPendingConfirmation(null);

      const processMsg: ChatMessage = {
        id: `workflow-${Date.now()}`,
        role: 'assistant',
        content: `专利申请流程已创建并自动启动！

任务编号：${result.task_id}

多智能体系统将依次执行：
1. 需求分析 — 结构化您的技术需求
2. 检索分析 — 现有技术检索与专利性评估
3. 专利撰写 — 生成申请文件
4. 质量审查 — 合规性审查`,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, processMsg]);
      void loadConversations();
    } catch (err) {
      setError(err instanceof Error ? err.message : '启动专利申请流程失败');
    } finally {
      setIsStartingWorkflow(false);
    }
  };

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) {
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  };

  return (
    <>
    <div className="fixed inset-x-0 bottom-0 top-16 flex min-h-0 overflow-hidden">
      {/* Sidebar Toggle (mobile) */}
      <button
        className="md:hidden fixed left-2 top-20 z-10 p-2 rounded-lg bg-canvas border border-hairline shadow-sm"
        onClick={() => setShowSidebar(!showSidebar)}
      >
        <ChevronRight className={clsx('w-4 h-4 text-slate transition-transform', showSidebar && 'rotate-180')} />
      </button>

      {/* Sidebar */}
      <aside
        className={clsx(
          'h-full min-h-0 w-80 flex-shrink-0 border-r border-hairline bg-surface/95 flex flex-col transition-transform',
          'md:relative md:translate-x-0',
          showSidebar ? 'translate-x-0' : '-translate-x-full absolute inset-y-0 z-20'
        )}
      >
        {/* Sidebar Header */}
        <div className="p-4 border-b border-hairline">
          <Button
            variant="default"
            size="sm"
            className="w-full"
            onClick={handleNewConversation}
          >
            <Plus className="w-4 h-4 mr-1" />
            新建对话
          </Button>
        </div>

        {/* Conversation List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loadingList ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-slate" />
            </div>
          ) : conversations.length === 0 ? (
            <div className="text-center py-8 px-4">
              <MessageSquare className="w-8 h-8 text-slate/50 mx-auto mb-2" />
              <p className="text-sm text-slate">暂无对话记录</p>
              <p className="text-xs text-slate/60 mt-1">点击上方按钮开始新对话</p>
            </div>
          ) : (
            conversations.map((conv) => {
              const convWorkflowState = conversationWorkflowState(conv);
              const statusDisplay = workflowStatusDisplay(convWorkflowState);

              return (
              <div
                key={conv.id}
                onClick={() => handleSelectConversation(conv.id)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleSelectConversation(conv.id); }}
                role="button"
                tabIndex={0}
                className={clsx(
                  'w-full text-left p-3 rounded-xl border transition-all group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green/40',
                  activeConvId === conv.id
                    ? 'border-brand-green/30 bg-brand-green/10 text-ink shadow-sm'
                    : 'border-transparent hover:border-hairline-strong hover:bg-canvas text-slate hover:text-ink'
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {conv.title || '新对话'}
                    </p>
                    <p className="text-xs text-slate/60 mt-0.5">
                      {conv.message_count} 条消息 · {formatDate(conv.updated_at)}
                    </p>
                    {(conv.linked_workflow_id || conv.workflow_task_id) && (
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <span className="inline-flex items-center gap-1 rounded-full bg-canvas px-2 py-0.5 text-[11px] font-medium text-slate ring-1 ring-hairline">
                        <WorkflowStatusIcon tone={statusDisplay.tone} />
                        <span>{statusDisplay.label}</span>
                        </span>
                        {(conv.linked_workflow_id || conv.workflow_task_id) && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              router.push(`/workflow/${encodeURIComponent((conv.linked_workflow_id || conv.workflow_task_id)! )}`);
                            }}
                            className="rounded-full px-2 py-0.5 text-[11px] font-medium text-brand-green-dark transition-colors hover:bg-brand-green/10 hover:text-brand-green focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green/40"
                            aria-label={`查看 ${conv.title || '当前对话'} 的工作流`}
                          >
                            查看工作流
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={(e) => handleDeleteConversation(e, conv.id)}
                    className="rounded-md p-1.5 opacity-0 transition-all hover:bg-red-50 focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-200 group-hover:opacity-100"
                    aria-label={`删除对话：${conv.title || '新对话'}`}
                    title="删除对话"
                  >
                    <Trash2 className="w-3.5 h-3.5 text-slate/40 hover:text-red-500" />
                  </button>
                </div>
              </div>
              );
            })
          )}
        </div>
      </aside>

      {/* Main Chat Area */}
      <div className="flex-1 flex h-full min-h-0 flex-col min-w-0 overflow-hidden">
        {/* Header */}
        <div className="flex-shrink-0 border-b border-hairline bg-canvas/95 px-6 py-3 backdrop-blur">
          <div className="flex items-center justify-between">
            <div>
              {editingTitle ? (
                <input
                  type="text"
                  value={editTitleValue}
                  onChange={(e) => setEditTitleValue(e.target.value)}
                  onBlur={handleSaveTitle}
                  onKeyDown={handleKeyDownTitle}
                  autoFocus
                  className="text-lg font-semibold text-ink bg-canvas border border-hairline rounded px-2 py-1 w-full focus:outline-none focus:border-accent"
                />
              ) : (
                <h1
                  className="text-lg font-semibold text-ink cursor-text"
                  onClick={handleStartEditingTitle}
                  title="点击重命名"
                >
                  {activeConvId ? (conversations.find((c) => c.id === activeConvId)?.title || '专利对话') : '新对话'}
                </h1>
              )}
              <p className="text-sm text-slate">
                {visibleWorkflowTaskId
                  ? '专利申请流程已启动'
                  : activeConvId
                  ? '与 AI 专利代理人沟通，完善技术方案'
                  : '描述您的发明创造，开始专利申请'}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {connectionStatus !== 'idle' && (
                <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${
                  connectionStatus === 'connected'
                    ? 'bg-green-50 text-green-700'
                    : 'bg-amber-50 text-amber-700'
                }`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${
                    connectionStatus === 'connected'
                      ? 'bg-green-500'
                      : connectionStatus === 'connecting'
                      ? 'bg-amber-500 animate-pulse'
                      : 'bg-red-500'
                  }`} />
                  {connectionStatus === 'connecting' ? '连接中' : connectionStatus === 'connected' ? '已连接' : '已断开'}
                </span>
              )}
              {activeConvId && (
                <>
                  {showSearch ? (
                    <div className="flex items-center gap-1">
                      <input
                        ref={searchInputRef}
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') {
                            setShowSearch(false);
                            setSearchQuery('');
                          }
                        }}
                        placeholder="搜索消息..."
                        autoFocus
                        className="w-48 text-sm border border-hairline rounded px-2 py-1.5 bg-white focus:outline-none focus:border-accent"
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => { setShowSearch(false); setSearchQuery(''); }}
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  ) : (
                    <Button variant="ghost" size="sm" onClick={() => setShowSearch(true)} title="搜索消息" aria-label="搜索消息">
                      <Search className="w-4 h-4" />
                    </Button>
                  )}
                </>
              )}
              {visibleWorkflowTaskId && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => router.push(`/workflow/${encodeURIComponent(visibleWorkflowTaskId)}`)}
                >
                  <Sparkles className="w-4 h-4 mr-1" />
                  查看工作流
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Unified CEO Dispatch Panel (stage roadmap + dispatch activities) */}
        {visibleWorkflowTaskId && (
          <WorkflowProgressStrip
            taskId={visibleWorkflowTaskId}
            currentState={visibleWorkflowState}
            refreshKey={isLoading ? 1 : 0}
            dispatchActivities={dispatchActivities}
            isStreaming={isLoading}
          />
        )}

        {/* Messages */}
        <div className="min-h-0 flex-1 overflow-y-auto bg-surface/35">
          <div className="mx-auto flex min-h-full max-w-5xl flex-col space-y-6 px-4 pb-44 pt-6 md:px-6">

            {isLoadingConv ? (
              <div className="flex justify-center py-12">
                <Loader2 className="w-6 h-6 animate-spin text-brand-green-dark" />
              </div>
            ) : !activeConvId && messages.length === 1 && messages[0]?.id === 'welcome' ? (
              <div className="flex min-h-0 flex-1 flex-col items-center justify-center text-center">
                <MessageSquare className="w-12 h-12 text-slate/30 mb-4" />
                <h2 className="text-lg font-semibold text-ink mb-2">开始新的专利对话</h2>
                <p className="text-sm text-slate max-w-md mb-6">
                  描述您的发明创造，AI 专利代理人将帮助您梳理技术方案、评估专利价值，并生成专业的专利申请文件。
                </p>
              </div>
            ) : (searchQuery ? filteredMessages : messages).length === 0 ? (
              <div className="flex min-h-0 flex-1 flex-col items-center justify-center text-center">
                <Bot className="w-10 h-10 text-slate/30 mb-3" />
                <p className="text-sm text-slate">{searchQuery ? '未找到匹配的消息' : '对话为空，发送第一条消息开始'}</p>
              </div>
            ) : (
              (searchQuery ? filteredMessages : messages).reduce<React.ReactNode[]>((acc: React.ReactNode[], msg: ChatMessage, idx: number) => {
                const items = searchQuery ? filteredMessages : messages;
                const prevMsg = idx > 0 ? items[idx - 1] : null;
                const msgDate = new Date(msg.timestamp);
                const dateStr = msgDate.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
                const prevDateStr = prevMsg
                  ? new Date(prevMsg.timestamp).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
                  : null;

                // Insert date separator when date changes (always show for first message)
                if (!prevMsg || dateStr !== prevDateStr) {
                  const label = dateStr === new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
                    ? '今天'
                    : (() => {
                        const y = new Date(); y.setDate(y.getDate() - 1);
                        if (dateStr === y.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })) return '昨天';
                        return dateStr;
                      })();
                  acc.push(
                    <div key={`date-${dateStr}`} className="flex justify-center py-1">
                      <span className="text-[11px] text-slate/50 bg-hairline-soft px-2.5 py-0.5 rounded-full">{label}</span>
                    </div>
                  );
                }

                if (msg.role === 'system') {
                  const isError = msg.metadata?.tone === 'error';
                  acc.push(
                    <div key={msg.id} className="flex justify-center" data-testid="chat-system-message">
                      <div
                        className={clsx(
                          'flex max-w-xl items-center gap-2 rounded-lg border px-3 py-2 text-xs',
                          isError
                            ? 'border-red-100 bg-red-50 text-red-500'
                            : 'border-hairline bg-hairline-soft text-slate'
                        )}
                      >
                        <AlertCircle className="h-4 w-4 flex-shrink-0" />
                        <span>{msg.content}</span>
                      </div>
                    </div>
                  );
                  return acc;
                }

                {(() => {
                  // 对于 assistant 消息，解析内容判断是否需要显示消息容器
                  const parsedContent = msg.role === 'assistant' && !msg.isStreaming ? parseMessageContent(msg.content) : null;
                  const hasConclusion = !parsedContent || parsedContent.conclusion;
                  const hasInteraction = parsedContent?.interaction;
                  const hasEmptyContent = !msg.content || !msg.content.trim();
                  
                  // 如果消息内容完全为空，不显示消息容器
                  if (msg.role === 'assistant' && !msg.isStreaming && hasEmptyContent) {
                    // 如果有活动日志，仍然显示活动日志
                    if (msg.agent_events && msg.agent_events.length > 0) {
                      acc.push(
                        <div
                          key={msg.id}
                          data-testid="chat-message-assistant-empty"
                          className="flex gap-3 justify-start"
                        >
                          <div className="flex-shrink-0 mt-1">
                            <div className="w-9 h-9 rounded-full bg-brand-green flex items-center justify-center">
                              <Bot className="w-4.5 h-4.5 text-ink" />
                            </div>
                          </div>
                          <div className="order-1 max-w-[760px]">
                            <AgentActivityLog events={msg.agent_events} className="-mx-1 mt-2" />
                            <p className="text-[11px] text-slate/60 mt-1 px-1">
                              {new Date(msg.timestamp).toLocaleTimeString('zh-CN', {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </p>
                          </div>
                        </div>
                      );
                    }
                    return acc;
                  }
                  
                  // 如果没有结论但有交互过程，只显示交互面板和活动日志
                  if (msg.role === 'assistant' && !msg.isStreaming && !hasConclusion && hasInteraction) {
                    acc.push(
                      <div
                        key={msg.id}
                        data-testid="chat-message-assistant-interaction-only"
                        className="flex gap-3 justify-start"
                      >
                        <div className="flex-shrink-0 mt-1">
                          <div className="w-9 h-9 rounded-full bg-brand-green flex items-center justify-center">
                            <Bot className="w-4.5 h-4.5 text-ink" />
                          </div>
                        </div>
                        <div className="order-1 max-w-[760px]">
                          <InteractionPanel interaction={parsedContent.interaction} />
                          {msg.agent_events && msg.agent_events.length > 0 && (
                            <AgentActivityLog events={msg.agent_events} className="-mx-1 mt-2" />
                          )}
                          <p className="text-[11px] text-slate/60 mt-1 px-1">
                            {new Date(msg.timestamp).toLocaleTimeString('zh-CN', {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </p>
                        </div>
                      </div>
                    );
                    return acc;
                  }
                  
                  // 正常消息渲染
                  acc.push(
                    <div
                      key={msg.id}
                      data-testid={msg.type === 'file' ? 'chat-file-message' : `chat-message-${msg.role}`}
                      className={clsx(
                        'flex gap-3',
                        msg.role === 'user' ? 'justify-end' : 'justify-start'
                      )}
                    >
                      {(msg.role === 'assistant' || msg.role === 'agent') && (
                        <div className="flex-shrink-0 mt-1">
                          <div className="w-9 h-9 rounded-full bg-brand-green flex items-center justify-center">
                            <Bot className="w-4.5 h-4.5 text-ink" />
                          </div>
                        </div>
                      )}

                      <div className={clsx(msg.role === 'user' ? 'order-1 max-w-[680px]' : 'order-1 max-w-[760px]')}>
                        {msg.type === 'file' && !msg.content ? (
                          <div className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-hairline bg-canvas text-sm text-ink">
                            <FileText className="w-4 h-4 text-slate-600 flex-shrink-0" />
                            <span className="font-medium truncate max-w-[240px]">
                              {(msg.metadata?.filename as string) || '上传文件'}
                            </span>
                            <span className="text-xs text-slate/70 flex-shrink-0">
                              {((msg.metadata?.file_size as number) || 0) > 0
                                ? `${Math.round(((msg.metadata?.file_size as number) || 0) / 1024)} KB`
                                : ''}
                            </span>
                          </div>
                        ) : (
                          <div className="relative group">
                            <div
                              className={clsx(
                                'rounded-2xl text-sm leading-relaxed shadow-sm',
                                msg.role === 'user'
                                  ? 'bg-brand-green text-ink rounded-br-md'
                                  : 'border border-hairline bg-canvas rounded-bl-md'
                              )}
                            >
                              {msg.type === 'file' && (
                                <div className="flex items-center gap-2 px-3.5 pt-2.5 pb-1.5 text-xs border-b border-ink/15">
                                  <FileText className="w-3.5 h-3.5 flex-shrink-0" />
                                  <span className="font-medium truncate">
                                    {(msg.metadata?.filename as string) || '上传文件'}
                                  </span>
                                  <span className="flex-shrink-0 opacity-80">
                                    {((msg.metadata?.file_size as number) || 0) > 0
                                      ? `${Math.round(((msg.metadata?.file_size as number) || 0) / 1024)} KB`
                                      : ''}
                                  </span>
                                </div>
                              )}
                              <div className={clsx('px-3.5 py-2.5', msg.role === 'user' ? 'whitespace-pre-wrap' : 'prose prose-sm max-w-none')}>
                                {msg.isStreaming && !msg.content ? (
                                  <div className="flex items-center gap-1.5 text-slate">
                                    <span>思考中</span>
                                    <span className="thinking-dot" />
                                    <span className="thinking-dot" />
                                    <span className="thinking-dot" />
                                  </div>
                                ) : msg.role === 'user' ? (
                                  msg.content
                                ) : (
                                  <>
                                    <div className={msg.isStreaming ? 'streaming-text streaming-cursor' : 'streaming-text'}>
                                      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                                        {msg.isStreaming ? msg.content : (parsedContent?.conclusion || msg.content)}
                                      </ReactMarkdown>
                                    </div>
                                    {(msg.role === 'assistant' || msg.role === 'agent') && (msg.tool_calls?.length || msg.skill_uses?.length) ? (
                                      <ToolCallCard
                                        toolCalls={msg.tool_calls}
                                        skillUses={msg.skill_uses}
                                        isStreaming={msg.isStreaming}
                                      />
                                    ) : null}
                                  </>
                                )}
                              </div>
                            </div>
                            {msg.role === 'assistant' && !msg.isStreaming && msg.content && (
                              <button
                                onClick={() => handleCopy(msg.id, msg.content)}
                                className="absolute -top-2 right-2 p-1 rounded-md bg-white border border-hairline shadow-sm opacity-0 group-hover:opacity-100 transition-opacity hover:bg-slate-50"
                                title="复制消息"
                                aria-label="复制消息"
                              >
                                {copiedId === msg.id ? (
                                  <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />
                                ) : (
                                  <Copy className="w-3.5 h-3.5 text-slate-500" />
                                )}
                              </button>
                            )}
                          </div>
                        )}
                        {/* 交互过程展开面板 */}
                        {msg.role === 'assistant' && !msg.isStreaming && msg.content && hasInteraction && (
                          <InteractionPanel interaction={parsedContent!.interaction} />
                        )}
                        {(msg.role === 'assistant' || msg.role === 'agent') && msg.agent_events && msg.agent_events.length > 0 && (
                          <AgentActivityLog events={msg.agent_events} className="-mx-1 mt-2" />
                        )}
                        <p className="text-[11px] text-slate/60 mt-1 px-1">
                          {new Date(msg.timestamp).toLocaleTimeString('zh-CN', {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </p>
                      </div>

                      {msg.role === 'user' && (
                        <div className="flex-shrink-0 mt-1">
                          <div className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center">
                            <User className="w-4.5 h-4.5 text-slate-600" />
                          </div>
                        </div>
                      )}
                    </div>
                  );
                  return acc;
                })()}
                return acc;
              }, [])
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Workflow Recommendation Banner */}
        {recommendStartWorkflow && activeConvId && !workflowTaskId && (
          <div className="flex-shrink-0 border-t border-hairline bg-green-50 px-6 py-3">
            <div className="max-w-4xl mx-auto flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-green-600" />
                <p className="text-sm text-green-800">
                  {suggestedTitle
                    ? `技术方案已整理完毕：「${suggestedTitle}」。是否启动正式专利申请？`
                    : '技术方案已基本清晰，可以启动正式专利申请流程。'}
                </p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <Button
                  size="sm"
                  onClick={() => handleStartWorkflow()}
                  disabled={isStartingWorkflow}
                  className="bg-green-600 hover:bg-green-700"
                >
                  {isStartingWorkflow ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <FileText className="w-4 h-4 mr-1" />
                  )}
                  启动专利申请
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setRecommendStartWorkflow(false)}
                  disabled={isStartingWorkflow}
                >
                  稍后
                </Button>
              </div>
            </div>
          </div>
        )}

        {pendingConfirmation && !recommendStartWorkflow && !workflowTaskId && (
          <div className="z-10 flex-shrink-0 border-t border-amber-200/80 bg-amber-50/95 px-4 py-3 shadow-[0_-12px_30px_rgba(0,30,43,0.08)] backdrop-blur">
            <div className="mx-auto max-w-5xl">
              <div className="rounded-2xl border border-amber-200 bg-white px-4 py-3 shadow-sm" role="group" aria-label="待确认的问题">
                <p className="mb-3 flex items-start gap-2 text-sm font-semibold text-amber-900">
                  <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
                  <span>
                  {pendingConfirmation.question}
                  </span>
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  {pendingConfirmation.options.length > 0 ? (
                    pendingConfirmation.options.map((opt, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => handleConfirmationAnswer(opt)}
                        className="min-h-9 rounded-full border border-amber-300 bg-amber-50 px-3.5 py-1.5 text-sm font-medium text-amber-800 transition-colors hover:border-amber-400 hover:bg-amber-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300"
                      >
                        {opt}
                      </button>
                    ))
                  ) : (
                    <p className="text-sm text-slate/60">请在输入框中回答</p>
                  )}
                  <button
                    type="button"
                    onClick={() => setPendingConfirmation(null)}
                    className="ml-auto min-h-9 rounded-full px-3.5 py-1.5 text-sm text-slate/60 transition-colors hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
                  >
                    跳过
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Input Area */}
        <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-hairline bg-canvas/98 px-4 py-3 shadow-[0_-10px_24px_rgba(0,30,43,0.08)] backdrop-blur md:left-80">
          <div className="mx-auto max-w-5xl">
            {pendingFile && (
              <div className="mb-2 flex items-center gap-2 px-3 py-2 rounded-lg border border-hairline bg-canvas text-sm">
                <FileText className="w-4 h-4 text-slate-600 flex-shrink-0" />
                <span className="font-medium truncate max-w-[280px]">
                  {pendingFile.name}
                </span>
                <span className="text-xs text-slate/70 flex-shrink-0">
                  {pendingFile.size >= 1024 * 1024
                    ? `${(pendingFile.size / 1024 / 1024).toFixed(1)} MB`
                    : `${Math.round(pendingFile.size / 1024)} KB`}
                </span>
                <span className="text-xs text-slate/50 ml-1">点击发送后上传</span>
                <button
                  type="button"
                  onClick={() => setPendingFile(null)}
                  disabled={isUploadingFile}
                  className="ml-auto p-1.5 rounded-md hover:bg-slate-100 text-slate-500 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green/40"
                  title="移除文件"
                  aria-label="移除待上传文件"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
            <div className="flex gap-2">
              <input
                data-testid="chat-file-input"
                ref={fileInputRef}
                type="file"
                accept=".txt,.docx,.pdf"
                onChange={handleFileSelected}
                className="hidden"
              />
              <Button
                type="button"
                variant="ghost"
                size="md"
                onClick={() => fileInputRef.current?.click()}
                disabled={!!pendingFile || isUploadingFile || isLoading || isLoadingConv || isStartingWorkflow}
                className="self-end"
                title="选择交底书（.txt / .docx / .pdf）"
                aria-label="选择交底书文件"
              >
                <Paperclip className="w-4 h-4" />
              </Button>
              <textarea
                data-testid="chat-input"
                ref={inputRef}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  e.target.style.height = 'auto';
                  e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={activeConvId ? '继续补充技术细节...（可点击 📎 选择交底书 .txt / .docx / .pdf）' : '描述您的发明创造...（可点击 📎 选择交底书 .txt / .docx / .pdf）'}
                className="flex-1 overflow-y-auto rounded-lg border border-hairline bg-white px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-green focus:border-brand-green placeholder:text-slate/60"
                rows={1}
                autoFocus
                disabled={isLoading || isLoadingConv || isStartingWorkflow || isUploadingFile}
              />
              <Button
                data-testid="chat-send-button"
                onClick={() => handleSend()}
                disabled={(!input.trim() && !pendingFile) || isLoading || isLoadingConv || isUploadingFile}
                isLoading={isLoading || isUploadingFile}
                className="self-end"
                aria-label="发送消息"
              >
                {!(isLoading || isUploadingFile) && <Send className="w-4 h-4" />}
              </Button>
            </div>
            <p className="text-xs text-slate/50 mt-1.5 text-center">
              Enter 发送 · Shift+Enter 换行 · 选择 .txt / .docx / .pdf 交底书后随消息一起发送
            </p>
          </div>
        </div>
      </div>
    </div>
      <ConfirmDialog
        open={deleteConfirmId !== null}
        title="删除对话"
        message="确定要删除此对话吗？删除后无法恢复。"
        confirmLabel="确认删除"
        variant="danger"
        onConfirm={executeDeleteConversation}
        onCancel={() => setDeleteConfirmId(null)}
      />
    </>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatPageContent />
    </Suspense>
  );
}
