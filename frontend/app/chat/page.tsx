'use client';

import { Suspense, useState, useRef, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Send, Bot, User, Sparkles, FileText, Loader2, Plus, Trash2,
  MessageSquare, ChevronRight, AlertCircle, CheckCircle2, Clock
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/Toast';
import { ToolCallCard } from '@/components/chat/ToolCallCard';
import { DispatchPanel, type DispatchActivity } from '@/components/chat/DispatchPanel';
import { clsx } from 'clsx';
import { conversationApi, workflowApi } from '@/lib/api';
import type { ConversationSummary } from '@/lib/api';
import type { ChatMessage } from '@/types';

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

function ChatPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const convIdFromParam = searchParams.get('conv_id');
  const taskIdFromParam = searchParams.get('task_id');

  // Conversation list
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loadingList, setLoadingList] = useState(true);

  // Active conversation
  const [activeConvId, setActiveConvId] = useState<string | null>(convIdFromParam);
  const [messages, setMessages] = useState<ChatMessage[]>([createWelcomeMessage()]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingConv, setIsLoadingConv] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSidebar, setShowSidebar] = useState(true);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  // Workflow state
  const [workflowTaskId, setWorkflowTaskId] = useState<string | null>(null);
  const [workflowState, setWorkflowState] = useState<string | null>(null);
  const [isStartingWorkflow, setIsStartingWorkflow] = useState(false);

  // Recommendations from backend
  const [recommendStartWorkflow, setRecommendStartWorkflow] = useState(false);
  const [suggestedTitle, setSuggestedTitle] = useState<string | null>(null);

  // Dispatch activities (CEO → specialist calls)
  const [dispatchActivities, setDispatchActivities] = useState<DispatchActivity[]>([]);

  const { addToast } = useToast();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sendingRef = useRef(false);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

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
    setIsLoadingConv(true);
    setError(null);
    try {
      const detail = await conversationApi.get(convId);
      setMessages(detail.messages.length > 0 ? detail.messages : [createWelcomeMessage()]);
      setWorkflowTaskId(detail.workflow_task_id ?? null);
      setWorkflowState(detail.workflow_state ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载对话失败');
      setMessages([createWelcomeMessage()]);
    } finally {
      setIsLoadingConv(false);
    }
  }, []);

  const initialMountDone = useRef(false);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    if (!initialMountDone.current) {
      initialMountDone.current = true;
      if (convIdFromParam) {
        void loadConversation(convIdFromParam);
      } else {
        setMessages([createWelcomeMessage()]);
        setWorkflowTaskId(null);
        setWorkflowState(null);
      }
    } else if (convIdFromParam && convIdFromParam !== activeConvId) {
      setActiveConvId(convIdFromParam);
      void loadConversation(convIdFromParam);
    }
  }, [convIdFromParam, activeConvId, loadConversation]);

  useEffect(() => {
    if (!taskIdFromParam || convIdFromParam) return;

    setWorkflowTaskId(taskIdFromParam);
    setWorkflowState(null);

    workflowApi.get(taskIdFromParam).then((workflow) => {
      setWorkflowState(workflow.current_state);
    }).catch(() => {});
  }, [taskIdFromParam, convIdFromParam]);

  // Create new conversation
  const handleNewConversation = async () => {
    setActiveConvId(null);
    setMessages([createWelcomeMessage()]);
    setWorkflowTaskId(null);
    setWorkflowState(null);
    setRecommendStartWorkflow(false);
    setSuggestedTitle(null);
    setError(null);
    router.replace('/chat');
  };

  // Select conversation
  const handleSelectConversation = (convId: string) => {
    setActiveConvId(convId);
    setWorkflowTaskId(null);
    setWorkflowState(null);
    setRecommendStartWorkflow(false);
    setSuggestedTitle(null);
    router.replace(`/chat?conv_id=${encodeURIComponent(convId)}`);
    // Sidebar auto-hides on mobile
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
  const handleSend = async () => {
    const content = input.trim();
    if (!content || isLoading || sendingRef.current) return;
    sendingRef.current = true;

    const userMsg: ChatMessage = {
      id: `local-user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);
    setError(null);

    try {
      let convId = activeConvId;

      // If no active conversation, create one
      if (!convId) {
        const created = await conversationApi.create({
          user_id: 'default_user',
          title: content.slice(0, 80),
        });
        convId = created.id;
        setActiveConvId(convId);
        router.replace(`/chat?conv_id=${encodeURIComponent(convId)}`);
        void loadConversations();
      }

      // Create a streaming assistant message placeholder
      const streamMsgId = `assistant-stream-${Date.now()}`;
      const streamMsg: ChatMessage = {
        id: streamMsgId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        isStreaming: true,
        tool_calls: [],
        skill_uses: [],
      };
      setMessages((prev) => [...prev, streamMsg]);

      // Use streaming API
      conversationApi.chatStream(convId, { content }, {
        onThinking: () => {
          setMessages((prev) => prev.map((m) =>
            m.id === streamMsgId ? { ...m, content: m.content || '正在思考...' } : m
          ));
        },
        onSkillUse: (data) => {
          setMessages((prev) => prev.map((m) =>
            m.id === streamMsgId
              ? { ...m, skill_uses: [...(m.skill_uses || []), data] }
              : m
          ));
        },
        onToolCallStart: (data) => {
          setMessages((prev) => prev.map((m) =>
            m.id === streamMsgId
              ? { ...m, tool_calls: [...(m.tool_calls || []), { ...data, result: null, success: true }] }
              : m
          ));
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
          setMessages((prev) => prev.map((m) => {
            if (m.id !== streamMsgId) return m;
            const updatedCalls = (m.tool_calls || []).map((tc) =>
              tc.name === data.name && tc.result === null
                ? { ...tc, result: data.result, success: data.success, error: data.error }
                : tc
            );
            return { ...m, tool_calls: updatedCalls };
          }));
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
        onContent: (data) => {
          setMessages((prev) => prev.map((m) =>
            m.id === streamMsgId
              ? { ...m, content: data.content, isStreaming: false }
              : m
          ));
          if (data.has_recommendation) {
            setRecommendStartWorkflow(true);
          }
        },
        onDone: (data) => {
          // Replace streaming message with final persisted message
          setMessages((prev) => prev.map((m) =>
            m.id === streamMsgId
              ? { ...data.message, isStreaming: false }
              : m
          ));
          setIsLoading(false);
          sendingRef.current = false;
          if (data.has_recommendation) {
            setRecommendStartWorkflow(true);
          }
          void loadConversations();
        },
        onError: (errorMsg) => {
          setError(errorMsg);
          setMessages((prev) => prev.filter((m) => m.id !== streamMsgId));
          setIsLoading(false);
          sendingRef.current = false;
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '发送消息失败');
      sendingRef.current = false;
      setIsLoading(false);
    }
  };

  // Start workflow from conversation
  const handleStartWorkflow = async () => {
    if (!activeConvId || isStartingWorkflow) return;
    setIsStartingWorkflow(true);
    setError(null);

    try {
      const result = await conversationApi.createWorkflow(activeConvId);
      setWorkflowTaskId(result.task_id);
      setWorkflowState(result.status);
      setRecommendStartWorkflow(false);

      const processMsg: ChatMessage = {
        id: `workflow-${Date.now()}`,
        role: 'assistant',
        content: `专利申请流程已启动！

任务编号：${result.task_id}

多智能体系统将依次执行：
1. 需求分析 — 结构化您的技术需求
2. 检索分析 — 现有技术检索与专利性评估
3. 专利撰写 — 生成申请文件
4. 质量审查 — 合规性审查

您可以[查看工作流进度](/workflow/${result.task_id})，也可以继续在这里补充细节。`,
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
    <div className="flex h-[calc(100vh-4rem)]">
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
          'w-72 flex-shrink-0 border-r border-hairline bg-surface flex flex-col transition-transform',
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
            conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => handleSelectConversation(conv.id)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleSelectConversation(conv.id); }}
                role="button"
                tabIndex={0}
                className={clsx(
                  'w-full text-left p-3 rounded-lg transition-colors group cursor-pointer',
                  activeConvId === conv.id
                    ? 'bg-brand-green/10 text-ink'
                    : 'hover:bg-hairline text-slate hover:text-ink'
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
                    {conv.workflow_state && (
                      <div className="flex items-center gap-1 mt-1">
                        {conv.workflow_state === 'completed' ? (
                          <CheckCircle2 className="w-3 h-3 text-green-600" />
                        ) : (
                          <Clock className="w-3 h-3 text-amber-500" />
                        )}
                        <span className="text-xs text-slate/60">
                          {conv.workflow_state === 'completed' ? '已完成' :
                           conv.workflow_state === 'failed' ? '已失败' :
                           conv.workflow_state === 'initial' ? '待启动' : '进行中'}
                        </span>
                        {conv.workflow_task_id && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              router.push(`/workflow/${encodeURIComponent(conv.workflow_task_id!)}`);
                            }}
                            className="ml-2 text-xs text-brand-green-dark hover:text-brand-green font-medium underline-offset-2 hover:underline"
                          >
                            查看工作流
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={(e) => handleDeleteConversation(e, conv.id)}
                    className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-50 transition-all"
                  >
                    <Trash2 className="w-3.5 h-3.5 text-slate/40 hover:text-red-500" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="border-b border-hairline bg-canvas px-6 py-3">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold text-ink">
                {activeConvId ? (conversations.find((c) => c.id === activeConvId)?.title || '专利对话') : '新对话'}
              </h1>
              <p className="text-sm text-slate">
                {workflowTaskId
                  ? '专利申请流程已启动'
                  : activeConvId
                  ? '与 AI 专利代理人沟通，完善技术方案'
                  : '描述您的发明创造，开始专利申请'}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {workflowTaskId && (
                <>
                  <Badge
                    variant="soft"
                    color={
                      workflowState === 'completed' ? 'green' :
                      workflowState === 'failed' || workflowState === 'cancelled' ? 'orange' : 'blue'
                    }
                  >
                    <CheckCircle2 className="w-3 h-3 mr-1" />
                    {workflowState === 'completed' ? '已完成' :
                     workflowState === 'failed' ? '已失败' :
                     workflowState === 'cancelled' ? '已取消' : '流程中'}
                  </Badge>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => router.push(`/workflow/${encodeURIComponent(workflowTaskId)}`)}
                  >
                    <Sparkles className="w-4 h-4 mr-1" />
                    查看工作流
                  </Button>
                  {workflowState === 'completed' && (
                    <Button
                      size="sm"
                      variant="default"
                      onClick={() => router.push(`/result/${encodeURIComponent(workflowTaskId)}`)}
                    >
                      <FileText className="w-4 h-4 mr-1" />
                      查看结果
                    </Button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        {/* Dispatch Status Panel */}
        <DispatchPanel
          activities={dispatchActivities}
          workflowTaskId={workflowTaskId}
          isActive={isLoading}
        />

        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto px-4 py-6 space-y-5">
            {error && (
              <Card className="p-4 border border-red-200 bg-red-50">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-red-500" />
                  <p className="text-sm text-red-700">{error}</p>
                </div>
              </Card>
            )}

            {isLoadingConv ? (
              <div className="flex justify-center py-12">
                <Loader2 className="w-6 h-6 animate-spin text-brand-green-dark" />
              </div>
            ) : (
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className={clsx(
                    'flex gap-3',
                    msg.role === 'user' ? 'justify-end' : 'justify-start'
                  )}
                >
                  {msg.role === 'assistant' && (
                    <div className="flex-shrink-0 mt-1">
                      <div className="w-9 h-9 rounded-full bg-brand-green flex items-center justify-center">
                        <Bot className="w-4.5 h-4.5 text-ink" />
                      </div>
                    </div>
                  )}

                  <div className={clsx('max-w-xl', msg.role === 'user' ? 'order-1' : 'order-1')}>
                    <div
                      className={clsx(
                        'p-3.5 rounded-xl text-sm leading-relaxed whitespace-pre-wrap',
                        msg.role === 'user'
                          ? 'bg-brand-green text-ink rounded-br-md'
                          : 'bg-canvas border border-hairline rounded-bl-md'
                      )}
                    >
                      {msg.content}
                      {msg.role === 'assistant' && (msg.tool_calls?.length || msg.skill_uses?.length) ? (
                        <ToolCallCard
                          toolCalls={msg.tool_calls}
                          skillUses={msg.skill_uses}
                          isStreaming={msg.isStreaming}
                        />
                      ) : null}
                    </div>
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
              ))
            )}

            {isLoading && (
              <div className="flex gap-3">
                <div className="flex-shrink-0 mt-1">
                  <div className="w-9 h-9 rounded-full bg-brand-green flex items-center justify-center">
                    <Bot className="w-4.5 h-4.5 text-ink" />
                  </div>
                </div>
                <Card className="p-3.5 bg-canvas border border-hairline rounded-bl-md">
                  <div className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin text-brand-green-dark" />
                    <span className="text-sm text-slate">思考中...</span>
                  </div>
                </Card>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Workflow Recommendation Banner */}
        {recommendStartWorkflow && activeConvId && !workflowTaskId && (
          <div className="border-t border-hairline bg-green-50 px-6 py-3">
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
                  onClick={handleStartWorkflow}
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

        {/* Input Area */}
        <div className="border-t border-hairline bg-canvas px-4 py-3">
          <div className="max-w-4xl mx-auto">
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={activeConvId ? '继续补充技术细节...' : '描述您的发明创造...'}
                className="flex-1 resize-none rounded-lg border border-hairline bg-white px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-green focus:border-brand-green placeholder:text-slate/60"
                rows={2}
                disabled={isLoading || isLoadingConv || isStartingWorkflow}
              />
              <Button
                onClick={handleSend}
                disabled={!input.trim() || isLoading || isLoadingConv}
                className="self-end"
              >
                {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </Button>
            </div>
            <p className="text-xs text-slate/50 mt-1.5 text-center">
              Enter 发送 · Shift+Enter 换行
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
