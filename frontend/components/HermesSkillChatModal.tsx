'use client';

import { useState } from 'react';
import {
  X,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ArrowRight,
  ArrowLeft,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { CodeBlock } from '@/components/ui/CodeBlock';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { hermesApi } from '@/lib/api';

interface HermesSkillChatModalProps {
  agentId: string;
  onClose: () => void;
  onSkillCreated: (skillData: { name: string; description: string; proficiency: number; keywords: string[] }) => void;
}

type Step = 'collect' | 'generating' | 'preview' | 'creating' | 'done';

interface ChatMsg {
  role: 'assistant' | 'user';
  content: string;
}

export default function HermesSkillChatModal({
  agentId,
  onClose,
  onSkillCreated,
}: HermesSkillChatModalProps) {
  const [step, setStep] = useState<Step>('collect');
  const [skillName, setSkillName] = useState('');
  const [skillDescription, setSkillDescription] = useState('');
  const [generatedSkill, setGeneratedSkill] = useState<{ name: string; description: string; proficiency: number; keywords: string[] } | null>(null);
  const [generatedContent, setGeneratedContent] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [chatHistory, setChatHistory] = useState<ChatMsg[]>([
    {
      role: 'assistant',
      content: '你好！我来帮你创建一个新的 Agent 技能。请告诉我：\n\n1. **技能名称**（2-6个中文字，简洁有力）\n2. **技能描述**（这个技能能做什么，越详细越好）\n\n我会根据你的描述自动推荐熟练度和关键词。',
    },
  ]);

  const handleGenerate = async () => {
    if (!skillDescription.trim()) {
      setMessage({ type: 'error', text: '请至少填写技能描述' });
      return;
    }

    setChatHistory(prev => [
      ...prev,
      { role: 'user', content: `名称: ${skillName || '（自动生成）'}\n描述: ${skillDescription}` },
    ]);

    setStep('generating');
    setIsLoading(true);
    setMessage(null);

    try {
      const result = await hermesApi.chatGenerateSkill(
        agentId,
        skillName.trim() || undefined,
        skillDescription.trim(),
      );

      if (result.success && result.skill_data) {
        const skillData = result.skill_data;
        setGeneratedSkill(skillData);
        setGeneratedContent(result.generated_content || '');
        setChatHistory(prev => [
          ...prev,
          {
            role: 'assistant',
            content: `技能已设计完成！\n\n• 名称: **${skillData.name}**\n• 熟练度: ${skillData.proficiency}\n• 关键词: ${skillData.keywords.join(', ')}\n\n请确认后点击"确认添加"将技能注册到 Agent。`,
          },
        ]);
        setStep('preview');
      } else {
        throw new Error(result.message || '生成失败');
      }
    } catch (e) {
      setMessage({ type: 'error', text: e instanceof Error ? e.message : '生成失败' });
      setStep('collect');
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirmCreate = () => {
    if (!generatedSkill) return;

    setStep('creating');
    setChatHistory(prev => [
      ...prev,
      { role: 'user', content: '确认添加' },
      { role: 'assistant', content: `✅ 技能「${generatedSkill.name}」已成功添加到 Agent！` },
    ]);

    setStep('done');
    setMessage({ type: 'success', text: `技能「${generatedSkill.name}」已创建` });
    onSkillCreated(generatedSkill);
    setTimeout(onClose, 2000);
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-3xl p-6 relative animate-in fade-in zoom-in-95 max-h-[85vh] flex flex-col">
        <button onClick={onClose} className="absolute top-4 right-4 p-1 hover:bg-slate-100 rounded transition-colors">
          <X className="w-5 h-5 text-slate" />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-purple-100 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-purple-700" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-ink">创建 Agent 技能</h3>
            <p className="text-sm text-slate">对话式引导：描述技能 → 预览配置 → 确认添加</p>
          </div>
        </div>

        {/* Progress */}
        <div className="flex items-center gap-2 mb-4 text-xs">
          <span className={`px-2 py-1 rounded ${step === 'collect' ? 'bg-purple-100 text-purple-700 font-medium' : 'bg-slate-100 text-slate'}`}>1. 描述技能</span>
          <ArrowRight className="w-3 h-3 text-slate-300" />
          <span className={`px-2 py-1 rounded ${['generating', 'preview'].includes(step) ? 'bg-purple-100 text-purple-700 font-medium' : 'bg-slate-100 text-slate'}`}>2. 预览配置</span>
          <ArrowRight className="w-3 h-3 text-slate-300" />
          <span className={`px-2 py-1 rounded ${['creating', 'done'].includes(step) ? 'bg-purple-100 text-purple-700 font-medium' : 'bg-slate-100 text-slate'}`}>3. 确认添加</span>
        </div>

        {/* Chat */}
        <div className="bg-slate-50 rounded-lg p-3 mb-4 max-h-28 overflow-auto text-sm space-y-1.5">
          {chatHistory.map((msg, i) => (
            <div key={i} className={msg.role === 'assistant' ? 'text-slate-700' : 'text-purple-700'}>
              <span className="font-medium">{msg.role === 'assistant' ? '🤖 ' : '👤 '}</span>
              <span className="whitespace-pre-wrap">{msg.content}</span>
            </div>
          ))}
          {isLoading && step === 'generating' && (
            <div className="flex items-center gap-2 text-slate">
              <Loader2 className="w-3 h-3 animate-spin" /> 正在通过 LLM 设计技能...
            </div>
          )}
        </div>

        {/* Step: Collect */}
        {step === 'collect' && (
          <div className="space-y-3 flex-1">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">技能名称 <span className="text-xs text-slate">(可选，不填则自动生成)</span></label>
              <Input placeholder="例如: 风险预判" value={skillName} onChange={(e) => setSkillName(e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">技能描述 *</label>
              <Textarea
                placeholder="详细描述这个技能能做什么，例如：根据技术方案的特征预判审查过程中可能遇到的驳回风险，并给出规避建议"
                value={skillDescription}
                onChange={(e) => setSkillDescription(e.target.value)}
                rows={3}
              />
            </div>
            <div className="flex justify-end">
              <Button onClick={handleGenerate} disabled={!skillDescription.trim()}>
                <Sparkles className="w-4 h-4 mr-1" /> 生成技能配置 <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
            </div>
          </div>
        )}

        {/* Step: Preview */}
        {step === 'preview' && generatedSkill && (
          <div className="flex-1 overflow-auto min-h-0 space-y-3">
            {/* Skill card */}
            <div className="bg-purple-50 rounded-lg p-4 border border-purple-100">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-slate">名称：</span>
                  <span className="font-medium text-ink">{generatedSkill.name}</span>
                </div>
                <div>
                  <span className="text-slate">熟练度：</span>
                  <span className="font-medium text-ink">{generatedSkill.proficiency}</span>
                </div>
                <div className="col-span-2">
                  <span className="text-slate">描述：</span>
                  <span className="text-ink">{generatedSkill.description}</span>
                </div>
                <div className="col-span-2">
                  <span className="text-slate">关键词：</span>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {generatedSkill.keywords.map((kw, i) => (
                      <span key={i} className="px-2 py-0.5 bg-white border border-purple-200 rounded-full text-xs text-purple-700">{kw}</span>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Generated content */}
            {generatedContent && (
              <div>
                <p className="text-xs font-medium text-slate mb-2">技能说明文档</p>
                <div className="max-h-40 overflow-auto">
                  <CodeBlock language="markdown">{generatedContent}</CodeBlock>
                </div>
              </div>
            )}

            <div className="flex justify-between pt-2">
              <Button variant="ghost" size="sm" onClick={() => { setStep('collect'); setGeneratedSkill(null); }}>
                <ArrowLeft className="w-4 h-4 mr-1" /> 返回修改
              </Button>
              <Button onClick={handleConfirmCreate} className="bg-purple-600 hover:bg-purple-700 text-white">
                <CheckCircle2 className="w-4 h-4 mr-1" /> 确认添加
              </Button>
            </div>
          </div>
        )}

        {/* Step: Creating / Done */}
        {step === 'done' && (
          <div className="flex flex-col items-center justify-center py-12">
            <CheckCircle2 className="w-12 h-12 text-green-500 mb-3" />
            <p className="text-lg font-medium text-ink">技能创建成功！</p>
            <p className="text-sm text-slate mt-1">已添加到 Agent，即将关闭...</p>
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