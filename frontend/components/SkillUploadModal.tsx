'use client';

import { useRef, useState } from 'react';
import {
  X,
  Upload,
  FileArchive,
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { hermesApi } from '@/lib/api';

interface SkillUploadModalProps {
  agentId: string;
  onClose: () => void;
  onSkillCreated: (skillData: {
    name: string;
    description: string;
    tags: string[];
    source_code?: string;
    source_markdown?: string;
  }) => void;
}

export default function SkillUploadModal({
  agentId,
  onClose,
  onSkillCreated,
}: SkillUploadModalProps) {
  const [skillName, setSkillName] = useState('');
  const [skillDescription, setSkillDescription] = useState('');
  const [tagsInput, setTagsInput] = useState('');
  const [markdown, setMarkdown] = useState('');
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [uploadMode, setUploadMode] = useState<'markdown' | 'zip' | 'both'>('markdown');
  const [isUploading, setIsUploading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.name.endsWith('.zip')) {
        setMessage({ type: 'error', text: '仅支持 ZIP 文件上传' });
        return;
      }
      setZipFile(file);
    }
  };

  const encodeZipAsBase64 = async (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        // Remove data URL prefix (data:application/zip;base64,)
        const base64 = result.split(',')[1] || result;
        resolve(base64);
      };
      reader.onerror = () => reject(new Error('文件读取失败'));
      reader.readAsDataURL(file);
    });
  };

  const handleUpload = async () => {
    if (!skillName.trim()) {
      setMessage({ type: 'error', text: '技能名称不能为空' });
      return;
    }

    setIsUploading(true);
    setMessage(null);

    try {
      const tags = tagsInput
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);

      let zipBase64: string | undefined;
      if (zipFile) {
        zipBase64 = await encodeZipAsBase64(zipFile);
      }

      const result = await hermesApi.uploadSkill(agentId, skillName.trim(), skillDescription.trim(), {
        markdown: markdown.trim() || undefined,
        zipBase64,
        tags: tags.length > 0 ? tags : undefined,
      });

      setMessage({ type: 'success', text: result.message });

      onSkillCreated({
        name: skillName.trim(),
        description: skillDescription.trim(),
        tags,
        source_code: result.files.length > 0
          ? result.files.map((f) => `# ${f.filename} (${f.size} bytes)`).join('\n')
          : undefined,
        source_markdown: markdown.trim() || undefined,
      });

      setTimeout(onClose, 1500);
    } catch (e) {
      setMessage({ type: 'error', text: e instanceof Error ? e.message : '上传失败' });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-2xl p-6 relative animate-in fade-in zoom-in-95 max-h-[85vh] flex flex-col">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 hover:bg-slate-100 rounded transition-colors"
        >
          <X className="w-5 h-5 text-slate" />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-xl bg-purple-100 flex items-center justify-center">
            <FileArchive className="w-5 h-5 text-purple-700" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-ink">安装 Hermes 技能包</h3>
            <p className="text-sm text-slate">上传 ZIP 包或直接输入 Markdown 技能描述</p>
          </div>
        </div>

        {/* Form */}
        <div className="space-y-4 flex-1 overflow-auto">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">技能名称</label>
              <Input
                placeholder="技能名称"
                value={skillName}
                onChange={(e) => setSkillName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                标签 <span className="text-xs text-slate">(逗号分隔)</span>
              </label>
              <Input
                placeholder="search, patent, analysis"
                value={tagsInput}
                onChange={(e) => setTagsInput(e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-ink mb-1">技能描述</label>
            <Input
              placeholder="描述技能的功能和用途"
              value={skillDescription}
              onChange={(e) => setSkillDescription(e.target.value)}
            />
          </div>

          {/* Upload mode selector */}
          <div>
            <label className="block text-sm font-medium text-ink mb-2">上传方式</label>
            <div className="flex gap-2">
              <button
                className={`px-4 py-2 rounded-lg text-sm border transition-colors ${
                  uploadMode === 'markdown' || uploadMode === 'both'
                    ? 'bg-purple-50 border-purple-300 text-purple-700'
                    : 'border-hairline text-slate hover:bg-slate-50'
                }`}
                onClick={() =>
                  setUploadMode((prev) =>
                    prev === 'markdown' ? 'zip' : prev === 'both' ? 'zip' : 'both',
                  )
                }
              >
                <FileText className="w-4 h-4 inline mr-1" />
                Markdown
              </button>
              <button
                className={`px-4 py-2 rounded-lg text-sm border transition-colors ${
                  uploadMode === 'zip' || uploadMode === 'both'
                    ? 'bg-purple-50 border-purple-300 text-purple-700'
                    : 'border-hairline text-slate hover:bg-slate-50'
                }`}
                onClick={() =>
                  setUploadMode((prev) =>
                    prev === 'zip' ? 'markdown' : prev === 'both' ? 'markdown' : 'both',
                  )
                }
              >
                <FileArchive className="w-4 h-4 inline mr-1" />
                ZIP 上传
              </button>
            </div>
          </div>

          {/* Markdown editor */}
          {(uploadMode === 'markdown' || uploadMode === 'both') && (
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                技能 Markdown 描述
              </label>
              <Textarea
                placeholder={`# Skill Name\n\n## Description\nDescribe your skill here...\n\n## Usage\nHow to use this skill...`}
                value={markdown}
                onChange={(e) => setMarkdown(e.target.value)}
                rows={8}
              />
            </div>
          )}

          {/* ZIP upload */}
          {(uploadMode === 'zip' || uploadMode === 'both') && (
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                ZIP 技能包
              </label>
              <div
                className="border-2 border-dashed border-hairline rounded-lg p-6 text-center cursor-pointer hover:border-brand-green transition-colors"
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={handleFileChange}
                />
                {zipFile ? (
                  <div>
                    <FileArchive className="w-8 h-8 mx-auto mb-2 text-brand-green" />
                    <p className="text-sm font-medium text-ink">{zipFile.name}</p>
                    <p className="text-xs text-slate">
                      {(zipFile.size / 1024).toFixed(1)} KB
                    </p>
                    <button
                      className="text-xs text-red-500 mt-1 hover:underline"
                      onClick={(e) => {
                        e.stopPropagation();
                        setZipFile(null);
                        if (fileInputRef.current) fileInputRef.current.value = '';
                      }}
                    >
                      移除文件
                    </button>
                  </div>
                ) : (
                  <div>
                    <Upload className="w-8 h-8 mx-auto mb-2 text-slate-400" />
                    <p className="text-sm text-slate">点击选择 ZIP 文件</p>
                    <p className="text-xs text-slate-400 mt-1">
                      应包含 SKILL.md + 脚本文件
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Message */}
        {message && (
          <div
            className={`mt-4 p-3 rounded-lg border text-sm flex items-center gap-2 ${
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

        {/* Footer */}
        <div className="mt-6 pt-4 border-t border-hairline flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button size="sm" onClick={handleUpload} disabled={isUploading}>
            {isUploading ? (
              <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> 安装中...</>
            ) : (
              <><Upload className="w-4 h-4 mr-1" /> 安装技能</>
            )}
          </Button>
        </div>
      </Card>
    </div>
  );
}
