'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import { useRouter } from 'next/navigation';
import {
  Send, Bot, User, Loader2, ArrowLeft, Sparkles, FileText, Search, Zap, Target, CheckCircle, Upload,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { clsx } from 'clsx';
import { toolsApi, type Tool } from '@/lib/api';

const TOOL_AGENT_ID = 'patent.tools_agent.v1';

const toolIcons: Record<string, typeof Target> = {
  'claim-drafting': FileText,
  'patent-mining': Search,
};

const displayNameMap: Record<string, string> = {
  'claim-drafting': '权项撰写',
  'patent-mining': '专利挖掘',
};

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: string;
  tool_name?: string;
  tool_result?: string;
  isStreaming?: boolean;
}

export default function ToolChatWorkspace() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const toolName = searchParams?.get('name') || '';
  
  const [tool, setTool] = useState<Tool | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId] = useState(() => `tool-${toolName}-${Date.now()}`);
  const [uploadedFiles, setUploadedFiles] = useState<{ name: string; content: string }[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (toolName) {
      loadTool();
    }
  }, [toolName]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function loadTool() {
    try {
      const toolData = await toolsApi.get(toolName);
      setTool(toolData);
      
      const displayName = displayNameMap[toolName] || toolName.replace(/-/g, ' ');
      const welcomeMessage: ChatMessage = {
        id: 'welcome',
        role: 'assistant',
        content: `欢迎使用 **${displayName}** 工具！\n\n${toolData.description}\n\n请告诉我您需要什么帮助，我将为您提供服务。\n\n您也可以上传技术交底书文件（支持 .txt、.md、.docx、.pdf），我会根据文件内容为您撰写权利要求书。`,
        timestamp: new Date().toISOString(),
      };
      setMessages([welcomeMessage]);
    } catch (error) {
      console.error('Failed to load tool:', error);
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setIsLoading(true);
    
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      
      try {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'}/tools/upload`, {
          method: 'POST',
          body: formData,
        });
        
        if (!response.ok) {
          throw new Error('文件上传失败');
        }
        
        const result = await response.json();
        const fileContent = result.content || '';
        
        setUploadedFiles((prev) => [...prev, { name: file.name, content: fileContent }]);
        
        const userMessage: ChatMessage = {
          id: `user-${Date.now()}-${i}`,
          role: 'user',
          content: `已上传文件：**${file.name}**\n\n文件内容预览：\n\`\`\`\n${fileContent.slice(0, 500)}${fileContent.length > 500 ? '...' : ''}\n\`\`\``,
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, userMessage]);
        
      } catch (error) {
        console.error('File upload error:', error);
      }
    }
    
    setIsLoading(false);
    e.target.value = '';
  }

  async function sendMessage() {
    if (!input.trim() && uploadedFiles.length === 0) return;
    if (isLoading) return;

    let fullContent = input.trim();
    if (uploadedFiles.length > 0) {
      fullContent += `\n\n已上传文件内容：\n${uploadedFiles.map(f => `\n--- ${f.name} ---\n${f.content}`).join('\n')}`;
    }

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: input.trim() || '请根据上传的文件内容进行分析',
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setUploadedFiles([]);
    setIsLoading(true);

    // 创建流式响应消息
    const streamMessageId = `assistant-${Date.now()}`;
    const streamMessage: ChatMessage = {
      id: streamMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      isStreaming: true,
    };
    setMessages((prev) => [...prev, streamMessage]);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'}/agents/${TOOL_AGENT_ID}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content: fullContent,
          session_id: sessionId,
          user_id: 'default_user',
          tool_name: toolName,
        }),
      });

      if (!response.ok) {
        throw new Error('请求失败');
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let accumulatedContent = '';

      if (reader) {
        let eventType = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                
                if (eventType === 'content_delta' || eventType === 'content') {
                  const content = data.delta || data.content || '';
                  accumulatedContent += content;
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === streamMessageId
                        ? { ...msg, content: accumulatedContent }
                        : msg
                    )
                  );
                } else if (eventType === 'thinking') {
                  console.log('Thinking:', data.message);
                } else if (eventType === 'tool_call_start') {
                  const toolCallMsg: ChatMessage = {
                    id: `tool-${Date.now()}`,
                    role: 'tool',
                    content: `正在调用工具: ${data.name}`,
                    timestamp: new Date().toISOString(),
                    tool_name: data.name,
                  };
                  setMessages((prev) => [...prev, toolCallMsg]);
                } else if (eventType === 'tool_call_end') {
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.tool_name === data.name
                        ? {
                            ...msg,
                            content: `工具 ${data.name} 执行完成`,
                            tool_result: data.result,
                          }
                        : msg
                    )
                  );
                } else if (eventType === 'done') {
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === streamMessageId
                        ? { ...msg, isStreaming: false }
                        : msg
                    )
                  );
                }
              } catch (e) {
                // 忽略解析错误
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === streamMessageId
            ? {
                ...msg,
                content: '抱歉，发生了错误。请稍后重试。',
                isStreaming: false,
              }
            : msg
        )
      );
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  }

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }, [input, isLoading]);

  const Icon = toolIcons[toolName] || Sparkles;
  const displayName = displayNameMap[toolName] || toolName.replace(/-/g, ' ');

  return (
    <div className="min-h-screen bg-canvas flex flex-col">
      {/* Header */}
      <header className="bg-surface border-b border-hairline px-4 py-3 flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => router.push('/tools')}>
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-brand-teal/20 text-brand-teal-deep flex items-center justify-center">
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <h1 className="font-semibold text-ink">{displayName}</h1>
            <p className="text-sm text-slate">{tool?.description || '加载中...'}</p>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={clsx(
                'flex gap-3',
                message.role === 'user' ? 'justify-end' : 'justify-start'
              )}
            >
              {message.role !== 'user' && (
                <div className="w-8 h-8 rounded-full bg-brand-teal/20 text-brand-teal-deep flex items-center justify-center flex-shrink-0">
                  {message.role === 'tool' ? (
                    <Zap className="w-4 h-4" />
                  ) : (
                    <Bot className="w-4 h-4" />
                  )}
                </div>
              )}
              <div
                className={clsx(
                  'rounded-xl px-4 py-3 max-w-[80%]',
                  message.role === 'user'
                    ? 'bg-brand-cyan text-white'
                    : message.role === 'tool'
                    ? 'bg-surface border border-hairline'
                    : 'bg-surface border border-hairline'
                )}
              >
                {message.role === 'tool' ? (
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <Zap className="w-4 h-4 text-brand-teal-deep" />
                      <span className="font-medium text-ink">{message.tool_name}</span>
                      <CheckCircle className="w-4 h-4 text-green-600" />
                    </div>
                    {message.tool_result && (
                      <div className="text-sm text-slate bg-canvas rounded-lg p-3 mt-2">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                          {message.tool_result}
                        </ReactMarkdown>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="prose prose-sm max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                      {message.content}
                    </ReactMarkdown>
                    {message.isStreaming && (
                      <span className="inline-block w-2 h-4 bg-brand-cyan animate-pulse ml-1" />
                    )}
                  </div>
                )}
              </div>
              {message.role === 'user' && (
                <div className="w-8 h-8 rounded-full bg-brand-cyan/20 text-brand-cyan-dark flex items-center justify-center flex-shrink-0">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="bg-surface border-t border-hairline px-4 py-4">
        <div className="max-w-3xl mx-auto flex gap-3">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            multiple
            accept=".txt,.md,.docx,.pdf"
            className="hidden"
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="p-3 rounded-xl border border-hairline"
          >
            <Upload className="w-5 h-5" />
          </Button>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入您的问题..."
            disabled={isLoading}
            className="flex-1 px-4 py-3 rounded-xl border border-hairline bg-canvas text-ink placeholder:text-muted focus:outline-none focus:border-brand-cyan focus:ring-2 focus:ring-brand-cyan/20 transition-all disabled:opacity-50"
          />
          <Button
            onClick={sendMessage}
            disabled={isLoading || (!input.trim() && uploadedFiles.length === 0)}
            className="px-6"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}