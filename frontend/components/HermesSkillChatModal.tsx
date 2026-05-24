'use client';

import { useState } from 'react';
import {
  X,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Code,
  FileText,
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

export default function HermesSkillChatModal({
  agentId,
  onClose,
  onSkillCreated,
}: HermesSkillChatModalProps) {
  const [skillName, setSkillName] = useState('');
  const [skillDescription, setSkillDescription] = useState('');
  const [generatedSkill, setGeneratedSkill] = useState<{ name: string; description: string; proficiency: number; keywords: string[] } | null>(null);
  const [generatedContent, setGeneratedContent] = useState<string>('');
  const [selectedFileIndex, setSelectedFileIndex] = useState(0);
  const [isGenerating, setIsGenerating] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleGenerate = async () => {
    if (!skillDescription.trim()) {
      setMessage({ type: 'error', text: '请填写技能描述' });
      return;
    }
    setIsGenerating(true);
    setMessage(null);
    setGeneratedSkill(null);
    setGeneratedContent('');
    try {
      const result = await hermesApi.chatGenerateSkill(
        agentId,
        skillName.trim() || undefined,
        skillDescription.trim(),
      );
      if (result.success && result.skill_data) {
        setGeneratedSkill(result.skill_data);
        setGeneratedContent(result.generated_content || '');
        setMessage({ type: 'success', text: '技能已生成，请查看后添加' });
      } else {
        throw new Error(result.message || '生成失败');
      }
    } catch (e) {
      setMessage({ type: 'error', text: e instanceof Error ? e.message : '生成失败' });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleAddSkill = async () => {
    if (!generatedSkill) {
      setMessage({ type: 'error', text: '请先生成技能' });
      return;
    }
    // In a real scenario, we might want to validate the skill data, but for now we add directly.
    // We'll call the agent API to update the skills (add the new skill).
    // However, note: the agentApi.updateSkills expects an array of skills (to replace).
    // We should fetch the current skills, add the new one, and then update.
    // But to keep it simple, we'll just call a hypothetical method to add a skill.
    // Since we don't have an explicit "add skill" API, we'll use the updateSkills method by merging.
    // We'll do it in two steps: get current skills, then add the new one and update.
    // But for the modal, we can just return the skill data and let the parent handle it.
    // The onSkillCreated callback is provided for that purpose.
    onSkillCreated(generatedSkill);
    // Auto-close after short delay
    setTimeout(onClose, 1500);
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
          <div className="w-10 h-10 rounded-xl bg-purple-100 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-purple-700" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-ink">Hermes 技能生成器</h3>
            <p className="text-sm text-slate">通过对话描述生成 Hermes 技能</p>
          </div>
        </div>

        {/* Form */}
        <div className="space-y-4 mb-6">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">技能名称（可选）</label>
              <Input
                placeholder="例如: multi_modal_analysis"
                value={skillName}
                onChange={(e) => setSkillName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">技能描述</label>
              <Input
                placeholder="描述技能的功能和用途"
                value={skillDescription}
                onChange={(e) => setSkillDescription(e.target.value)}
              />
            </div>
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
                <><Sparkles className="w-4 h-4 mr-1" /> 通过 LLM 生成</>
              )}
            </Button>
            {generatedSkill && (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleAddSkill}
                  className="bg-purple-600 hover:bg-purple-700"
                >
                  添加技能
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
        </div>

        {/* Generated skill preview — file-list view */}
        {generatedSkill && (() => {
          const skillNameSlug = generatedSkill.name || skillName || 'unnamed';
          const files: { path: string; content: string; lang: string }[] = [
            { path: `skills/${skillNameSlug}.json`, content: JSON.stringify(generatedSkill, null, 2), lang: 'json' },
          ];
          if (generatedContent) {
            files.push({ path: `skills/${skillNameSlug}_content.md`, content: generatedContent, lang: 'text' });
          }
          const selectedFile = files[selectedFileIndex] || files[0];
          return (
            <div className="flex-1 overflow-auto min-h-0 border-t border-hairline pt-4">
              <div className="flex items-center gap-2 mb-3">
                <Code className="w-4 h-4 text-ink" />
                <span className="text-sm font-medium text-ink">生成文件</span>
              </div>

              {/* File list */}
              <div className="border rounded-lg divide-y divide-hairline mb-3">
                {files.map((file, i) => (
                  <button
                    key={i}
                    className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 transition-colors ${
                      selectedFileIndex === i
                        ? 'bg-brand-green/10 text-brand-green-dark font-medium'
                        : 'bg-slate-50 hover:bg-slate-100 text-slate'
                    }`}
                    onClick={() => setSelectedFileIndex(i)}
                  >
                    <FileText className="w-4 h-4" />
                    <span className="font-mono text-xs">{file.path}</span>
                    <span className="ml-auto text-[10px] text-slate uppercase tracking-wider">
                      {file.lang === 'json' ? 'JSON' : 'Text'}
                    </span>
                  </button>
                ))}
              </div>

              {/* Content viewer */}
              <CodeBlock language={selectedFile.lang}>
                {selectedFile.content}
              </CodeBlock>
            </div>
          );
        })()}

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