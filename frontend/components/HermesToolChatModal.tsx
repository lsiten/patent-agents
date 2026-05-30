'use client';

import { useState } from 'react';
import {
  X,
  Wand2,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Code,
  FileText,
  Pencil,
  Eye,
  ArrowRight,
  ArrowLeft,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { CodeBlock } from '@/components/ui/CodeBlock';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { hermesApi } from '@/lib/api';

interface HermesToolChatModalProps {
  agentId: string;
  onClose: () => void;
  onToolCreated: (toolData: { name: string; description: string; source_code: string; is_hermes: boolean }) => void;
}

type Step = 'collect' | 'generating' | 'preview' | 'creating' | 'done';

interface ChatMsg {
  role: 'assistant' | 'user';
  content: string;
}

export default function HermesToolChatModal({
  agentId,
  onClose,
  onToolCreated,
}: HermesToolChatModalProps) {
  const [step, setStep] = useState<Step>('collect');
  const [toolName, setToolName] = useState('');
  const [toolDescription, setToolDescription] = useState('');
  const [parameters, setParameters] = useState('');
  const [generatedCode, setGeneratedCode] = useState('');
  const [editMode, setEditMode] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [chatHistory, setChatHistory] = useState<ChatMsg[]>([
    {
      role: 'assistant',
      content: '你好！我来帮你创建一个新的 Hermes 工具。请填写以下信息：\n\n1. **工具名称** — 英文 snake_case（如 patent_search）\n2. **功能描述** — 这个工具做什么\n3. **输入参数** — 需要哪些输入（每行一个 参数名=描述）\n\n填写完毕后点击"生成工具代码"。',
    },
  ]);

  const handleGenerate = async () => {
    if (!toolName.trim() || !toolDescription.trim()) {
      setMessage({ type: 'error', text: '请填写工具名称和功能描述' });
      return;
    }

    setChatHistory(prev => [
      ...prev,
      { role: 'user', content: `名称: ${toolName}\n描述: ${toolDescription}\n参数: ${parameters || '无'}` },
    ]);

    setStep('generating');
    setIsLoading(true);
    setMessage(null);

    try {
      const parsedParams: Record<string, string> = {};
      if (parameters.trim()) {
        parameters.split('\n').forEach((line) => {
          const [k, v] = line.split('=');
          if (k?.trim()) parsedParams[k.trim()] = (v || '').trim() || '参数描述';
        });
      }

      const result = await hermesApi.chatGenerateTool(
        agentId,
        toolName.trim(),
        toolDescription.trim(),
        Object.keys(parsedParams).length > 0 ? parsedParams : undefined,
      );

      setGeneratedCode(result.code);
      setChatHistory(prev => [
        ...prev,
        { role: 'assistant', content: '代码已生成！请查看预览，确认无误后点击"确认创建"。你也可以切换到编辑模式手动调整。' },
      ]);
      setStep('preview');
    } catch (e) {
      setMessage({ type: 'error', text: e instanceof Error ? e.message : '生成失败' });
      setStep('collect');
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirmCreate = async () => {
    setStep('creating');
    setIsLoading(true);
    setMessage(null);

    try {
      const validateResult = await hermesApi.validateTool(agentId, generatedCode);
      if (!validateResult.valid) {
        setMessage({ type: 'error', text: `代码验证失败: ${validateResult.error}` });
        setStep('preview');
        setIsLoading(false);
        return;
      }

      const result = await hermesApi.hotPlugTool(agentId, toolName.trim(), toolDescription.trim(), generatedCode);

      setChatHistory(prev => [
        ...prev,
        { role: 'user', content: '确认创建' },
        { role: 'assistant', content: `✅ ${result.message}` },
      ]);

      setStep('done');
      setMessage({ type: 'success', text: result.message });
      onToolCreated({ name: toolName.trim(), description: toolDescription.trim(), source_code: generatedCode, is_hermes: true });
      setTimeout(onClose, 2000);
    } catch (e) {
      setMessage({ type: 'error', text: e instanceof Error ? e.message : '创建失败' });
      setStep('preview');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-4xl p-6 relative animate-in fade-in zoom-in-95 max-h-[85vh] flex flex-col">
        <button onClick={onClose} className="absolute top-4 right-4 p-1 hover:bg-slate-100 rounded transition-colors">
          <X className="w-5 h-5 text-slate" />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-cyan-100 flex items-center justify-center">
            <Wand2 className="w-5 h-5 text-cyan-700" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-ink">创建 Hermes 工具</h3>
            <p className="text-sm text-slate">对话式引导：描述工具 → 预览代码 → 确认创建</p>
          </div>
        </div>

        {/* Progress */}
        <div className="flex items-center gap-2 mb-4 text-xs">
          <span className={`px-2 py-1 rounded ${step === 'collect' ? 'bg-cyan-100 text-cyan-700 font-medium' : 'bg-slate-100 text-slate'}`}>1. 描述工具</span>
          <ArrowRight className="w-3 h-3 text-slate-300" />
          <span className={`px-2 py-1 rounded ${['generating', 'preview'].includes(step) ? 'bg-cyan-100 text-cyan-700 font-medium' : 'bg-slate-100 text-slate'}`}>2. 预览代码</span>
          <ArrowRight className="w-3 h-3 text-slate-300" />
          <span className={`px-2 py-1 rounded ${['creating', 'done'].includes(step) ? 'bg-cyan-100 text-cyan-700 font-medium' : 'bg-slate-100 text-slate'}`}>3. 确认创建</span>
        </div>

        {/* Chat */}
        <div className="bg-slate-50 rounded-lg p-3 mb-4 max-h-28 overflow-auto text-sm space-y-1.5">
          {chatHistory.map((msg, i) => (
            <div key={i} className={msg.role === 'assistant' ? 'text-slate-700' : 'text-blue-700'}>
              <span className="font-medium">{msg.role === 'assistant' ? '🤖 ' : '👤 '}</span>
              <span className="whitespace-pre-wrap">{msg.content}</span>
            </div>
          ))}
          {isLoading && step === 'generating' && (
            <div className="flex items-center gap-2 text-slate">
              <Loader2 className="w-3 h-3 animate-spin" /> 正在通过 LLM 生成工具代码...
            </div>
          )}
        </div>

        {/* Step: Collect */}
        {step === 'collect' && (
          <div className="space-y-3 flex-1">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-ink mb-1">工具名称 *</label>
                <Input placeholder="patent_similarity_check" value={toolName} onChange={(e) => setToolName(e.target.value)} />
                <p className="text-xs text-slate mt-0.5">英文 snake_case</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1">功能描述 *</label>
                <Input placeholder="描述工具的核心功能" value={toolDescription} onChange={(e) => setToolDescription(e.target.value)} />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">输入参数 <span className="text-xs text-slate">(每行: 参数名=描述)</span></label>
              <Textarea placeholder="query=检索关键词&#10;limit=最大数量" value={parameters} onChange={(e) => setParameters(e.target.value)} rows={3} />
            </div>
            <div className="flex justify-end">
              <Button onClick={handleGenerate} disabled={!toolName.trim() || !toolDescription.trim()}>
                <Wand2 className="w-4 h-4 mr-1" /> 生成工具代码 <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
            </div>
          </div>
        )}

        {/* Step: Preview */}
        {step === 'preview' && generatedCode && (
          <div className="flex-1 overflow-auto min-h-0 space-y-3">
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-2 bg-slate-50 rounded px-3 py-1.5 border">
                <FileText className="w-4 h-4 text-slate" />
                <span className="font-mono text-xs text-slate">tools/{toolName}.py</span>
              </div>
              <button onClick={() => setEditMode(!editMode)} className="ml-auto text-xs flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-100 text-slate">
                {editMode ? <><Eye className="w-3.5 h-3.5" /> 预览</> : <><Pencil className="w-3.5 h-3.5" /> 编辑</>}
              </button>
            </div>
            {editMode ? (
              <textarea className="w-full h-56 font-mono text-sm p-3 border rounded-lg bg-slate-50 focus:outline-none focus:ring-2 focus:ring-cyan-400 resize-none" value={generatedCode} onChange={(e) => setGeneratedCode(e.target.value)} spellCheck={false} />
            ) : (
              <div className="max-h-56 overflow-auto"><CodeBlock language="python">{generatedCode}</CodeBlock></div>
            )}
            <div className="flex justify-between pt-2">
              <Button variant="ghost" size="sm" onClick={() => setStep('collect')}>
                <ArrowLeft className="w-4 h-4 mr-1" /> 返回修改
              </Button>
              <Button onClick={handleConfirmCreate} className="bg-cyan-600 hover:bg-cyan-700">
                <CheckCircle2 className="w-4 h-4 mr-1" /> 确认创建
              </Button>
            </div>
          </div>
        )}

        {/* Step: Creating */}
        {step === 'creating' && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-cyan-600" />
            <span className="ml-2 text-slate">正在验证并注册工具...</span>
          </div>
        )}

        {/* Step: Done */}
        {step === 'done' && (
          <div className="flex flex-col items-center justify-center py-12">
            <CheckCircle2 className="w-12 h-12 text-green-500 mb-3" />
            <p className="text-lg font-medium text-ink">工具创建成功！</p>
            <p className="text-sm text-slate mt-1">已注册到 Agent，即将关闭...</p>
          </div>
        )}

        {/* Message */}
        {message && (
          <div className={`mt-3 p-3 rounded-lg border text-sm flex items-center gap-2 ${message.type === 'success' ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'}`}>
            {message.type === 'success' ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
            {message.text}
          </div>
        )}

        {/* Footer */}
        <div className="mt-4 pt-3 border-t border-hairline flex justify-end">
          <Button size="sm" variant="ghost" onClick={onClose}>关闭</Button>
        </div>
      </Card>
    </div>
  );
}
