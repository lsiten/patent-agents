'use client';

import { useState } from 'react';
import {
  X,
  Wand2,
  CheckCircle2,
  AlertCircle,
  Zap,
  Loader2,
  Code,
  FileText,
  Pencil,
  Eye,
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

export default function HermesToolChatModal({
  agentId,
  onClose,
  onToolCreated,
}: HermesToolChatModalProps) {
  const [toolName, setToolName] = useState('');
  const [toolDescription, setToolDescription] = useState('');
  const [parameters, setParameters] = useState('');
  const [generatedCode, setGeneratedCode] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isPlugging, setIsPlugging] = useState(false);
  const [validationResult, setValidationResult] = useState<{
    valid: boolean;
    name: string | null;
    error: string | null;
  } | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleGenerate = async () => {
    if (!toolName.trim() || !toolDescription.trim()) {
      setMessage({ type: 'error', text: '请填写工具名称和描述' });
      return;
    }
    setIsGenerating(true);
    setMessage(null);
    setValidationResult(null);
    try {
      const parsedParams: Record<string, string> = {};
      if (parameters.trim()) {
        parameters.split('\n').forEach((line) => {
          const [k, v] = line.split('=');
          if (k?.trim()) parsedParams[k.trim()] = (v || '').trim() || 'description';
        });
      }
      const result = await hermesApi.chatGenerateTool(
        agentId,
        toolName.trim(),
        toolDescription.trim(),
        Object.keys(parsedParams).length > 0 ? parsedParams : undefined,
      );
      setGeneratedCode(result.code);
      setMessage({ type: 'success', text: '代码已生成，请验证后注册' });
    } catch (e) {
      setMessage({ type: 'error', text: e instanceof Error ? e.message : '生成失败' });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleValidate = async () => {
    if (!generatedCode.trim()) {
      setMessage({ type: 'error', text: '请先生成工具代码' });
      return;
    }
    setIsValidating(true);
    setMessage(null);
    try {
      const result = await hermesApi.validateTool(agentId, generatedCode);
      setValidationResult(result);
      setMessage({
        type: result.valid ? 'success' : 'error',
        text: result.valid ? '语法验证通过！' : `验证失败: ${result.error}`,
      });
    } catch (e) {
      setMessage({ type: 'error', text: e instanceof Error ? e.message : '验证失败' });
    } finally {
      setIsValidating(false);
    }
  };

  const handleHotPlug = async () => {
    if (!generatedCode.trim()) {
      setMessage({ type: 'error', text: '请先生成工具代码' });
      return;
    }
    setIsPlugging(true);
    setMessage(null);
    try {
      const result = await hermesApi.hotPlugTool(
        agentId,
        toolName.trim(),
        toolDescription.trim(),
        generatedCode,
      );
      setMessage({ type: 'success', text: result.message });
      onToolCreated({
        name: toolName.trim(),
        description: toolDescription.trim(),
        source_code: generatedCode,
        is_hermes: true,
      });
      // Auto-close after short delay
      setTimeout(onClose, 1500);
    } catch (e) {
      setMessage({ type: 'error', text: e instanceof Error ? e.message : '热插拔注册失败' });
    } finally {
      setIsPlugging(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-3xl p-6 relative animate-in fade-in zoom-in-95 max-h-[85vh] flex flex-col">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 hover:bg-slate-100 rounded transition-colors"
        >
          <X className="w-5 h-5 text-slate" />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-xl bg-cyan-100 flex items-center justify-center">
            <Wand2 className="w-5 h-5 text-cyan-700" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-ink">Hermes 工具生成器</h3>
            <p className="text-sm text-slate">通过对话描述生成 Hermes 工具代码</p>
          </div>
        </div>

        {/* Form */}
        <div className="space-y-4 mb-6">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">工具名称</label>
              <Input
                placeholder="例如: search_patent"
                value={toolName}
                onChange={(e) => setToolName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">工具描述</label>
              <Input
                placeholder="描述工具的功能"
                value={toolDescription}
                onChange={(e) => setToolDescription(e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              参数定义 <span className="text-xs text-slate">(可选，每行一个 param=description)</span>
            </label>
            <Textarea
              placeholder={`query=搜索关键词
limit=返回条数`}
              value={parameters}
              onChange={(e) => setParameters(e.target.value)}
              rows={2}
            />
          </div>

          {/* Action buttons */}
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={handleGenerate}
              disabled={isGenerating}
            >
              {isGenerating ? (
                <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> 生成中...</>
              ) : (
                <><Wand2 className="w-4 h-4 mr-1" /> 通过 LLM 生成</>
              )}
            </Button>
            {generatedCode && (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleValidate}
                  disabled={isValidating}
                >
                  {isValidating ? (
                    <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> 验证中...</>
                  ) : (
                    <><CheckCircle2 className="w-4 h-4 mr-1" /> 验证语法</>
                  )}
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleHotPlug}
                  disabled={isPlugging}
                  className="bg-cyan-600 hover:bg-cyan-700"
                >
                  {isPlugging ? (
                    <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> 注册中...</>
                  ) : (
                    <><Zap className="w-4 h-4 mr-1" /> 热插拔注册</>
                  )}
                </Button>
              </>
            )}
          </div>

          {/* Message */}
          {message && (
            <div
              className={`p-3 rounded-lg border text-sm flex items-center gap-2 ${
                message.type === 'success'
                  ? 'bg-green-50 border-green-200 text-green-700'
                  : 'bg-red-50 border-red-200 text-red-700'
              }`}
            >
              {message.type === 'success' ? (
                <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
              ) : (
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
              )}
              {message.text}
            </div>
          )}

          {/* Validation result detail */}
          {validationResult && !validationResult.valid && validationResult.error && (
            <div className="p-3 bg-red-50 rounded-lg border border-red-200 text-sm text-red-700">
              <p className="font-medium">错误详情:</p>
              <CodeBlock language="text">{validationResult.error}</CodeBlock>
            </div>
          )}
        </div>

        {/* Generated code — file-list view */}
        {generatedCode && (
          <div className="flex-1 overflow-auto min-h-0 border-t border-hairline pt-4">
            <div className="flex items-center gap-2 mb-3">
              <Code className="w-4 h-4 text-ink" />
              <span className="text-sm font-medium text-ink">生成文件</span>
              <button
                onClick={() => {
                  setEditMode(!editMode);
                }}
                className="ml-auto text-xs flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-100 transition-colors text-slate"
              >
                {editMode ? (
                  <><Eye className="w-3.5 h-3.5" /> 预览</>
                ) : (
                  <><Pencil className="w-3.5 h-3.5" /> 编辑</>
                )}
              </button>
            </div>
            {/* File list */}
            <div className="border rounded-lg divide-y divide-hairline mb-3">
              <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 text-sm">
                <FileText className="w-4 h-4 text-slate" />
                <span className="font-mono text-xs text-slate">tools/{toolName || 'unnamed'}.py</span>
                <span className="ml-auto text-[10px] text-slate uppercase tracking-wider">
                  Python
                </span>
              </div>
            </div>
            {/* Code viewer / editor */}
            {editMode ? (
              <textarea
                className="w-full h-64 font-mono text-sm p-4 border rounded-lg bg-slate-50 focus:outline-none focus:ring-2 focus:ring-brand-green resize-none"
                value={generatedCode}
                onChange={(e) => {
                  setGeneratedCode(e.target.value);
                  setValidationResult(null);
                }}
                spellCheck={false}
              />
            ) : (
              <CodeBlock language="python">{generatedCode}</CodeBlock>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="mt-4 pt-4 border-t border-hairline flex justify-end">
          <Button size="sm" variant="ghost" onClick={onClose}>
            关闭
          </Button>
        </div>
      </Card>
    </div>
  );
}
