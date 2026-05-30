'use client';

import { useCallback, useEffect, useState } from 'react';
import { X, Code, FileText, FolderOpen, RefreshCw, Info, Layers } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { CodeBlock } from '@/components/ui/CodeBlock';
import { hermesApi, type RelatedFileEntry, type RelatedFilesResponse } from '@/lib/api';

interface RelatedDetailModalProps {
  agentId: string;
  type: 'tool' | 'skill';
  name: string;
  itemId: string;
  onClose: () => void;
}

interface ToolStructure {
  class_name: string | null;
  description: string | null;
  parameters: { name: string; type: string; description: string }[];
  methods: { name: string; args: string[]; is_async: boolean }[];
  file_path: string | null;
  template: string;
}

interface SkillStructure {
  name: string;
  description: string;
  version: string;
  tags: string[];
  enabled: boolean;
  file: string;
  injection_method: string;
  injection_description: string;
  template: string;
}

const FILE_LANG_MAP: Record<string, string> = {
  ts: 'typescript',
  tsx: 'tsx',
  js: 'javascript',
  jsx: 'jsx',
  py: 'python',
  md: 'markdown',
  json: 'json',
  css: 'css',
  html: 'html',
  yaml: 'yaml',
  yml: 'yaml',
  sh: 'bash',
  toml: 'toml',
  txt: 'text',
};

function getFileLang(filename: string): string {
  const parts = filename.split('.');
  const ext = parts[parts.length - 1]?.toLowerCase() || '';
  return FILE_LANG_MAP[ext] || 'typescript';
}

export default function RelatedDetailModal({
  agentId,
  type,
  name,
  itemId,
  onClose,
}: RelatedDetailModalProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<(RelatedFilesResponse & { structure?: ToolStructure | SkillStructure }) | null>(null);
  const [selectedFile, setSelectedFile] = useState<RelatedFileEntry | null>(null);
  const [activeView, setActiveView] = useState<'structure' | 'files'>('structure');

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = type === 'tool'
        ? await hermesApi.getRelatedFiles(agentId, itemId)
        : await hermesApi.getRelatedFiles(agentId, undefined, itemId);
      setData(result as any);
      if (result.files.length > 0) {
        setSelectedFile(result.files[0]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载详情失败');
    } finally {
      setLoading(false);
    }
  }, [agentId, type, itemId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const structure = (data as any)?.structure as ToolStructure | SkillStructure | undefined;

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-5xl p-6 relative animate-in fade-in zoom-in-95 max-h-[85vh] flex flex-col">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 hover:bg-slate-100 rounded transition-colors"
        >
          <X className="w-5 h-5 text-slate" />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-brand-green/10 flex items-center justify-center">
            <FolderOpen className="w-5 h-5 text-brand-green" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-ink">
              {name} — {type === 'tool' ? '工具' : '技能'}详情
            </h3>
            <p className="text-sm text-slate">
              查看{type === 'tool' ? '工具' : '技能'}的完整结构、源码和创建模板
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={loadData}
            disabled={loading}
            className="ml-auto"
          >
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </Button>
        </div>

        {/* View Toggle */}
        <div className="flex gap-2 mb-4 border-b border-hairline pb-3">
          <button
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors flex items-center gap-1.5 ${
              activeView === 'structure'
                ? 'bg-brand-green/10 text-brand-green-dark'
                : 'text-slate hover:bg-slate-50'
            }`}
            onClick={() => setActiveView('structure')}
          >
            <Layers className="w-4 h-4" />
            结构信息
          </button>
          <button
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors flex items-center gap-1.5 ${
              activeView === 'files'
                ? 'bg-brand-green/10 text-brand-green-dark'
                : 'text-slate hover:bg-slate-50'
            }`}
            onClick={() => setActiveView('files')}
          >
            <Code className="w-4 h-4" />
            源码文件
          </button>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-16">
            <RefreshCw className="w-6 h-6 text-slate animate-spin" />
            <span className="ml-2 text-slate">加载中...</span>
          </div>
        )}

        {error && (
          <div className="p-4 bg-red-50 rounded-lg border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}

        {!loading && !error && data && activeView === 'structure' && structure && (
          <div className="flex-1 overflow-auto">
            {type === 'tool' && 'class_name' in structure && (
              <div className="space-y-4">
                {/* 基本信息 */}
                <div className="bg-slate-50 rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
                    <Info className="w-4 h-4" />
                    工具基本信息
                  </h4>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <span className="text-slate">类名：</span>
                      <code className="bg-white px-2 py-0.5 rounded border text-xs">
                        {(structure as ToolStructure).class_name || '未知'}
                      </code>
                    </div>
                    <div>
                      <span className="text-slate">文件：</span>
                      <code className="bg-white px-2 py-0.5 rounded border text-xs">
                        {(structure as ToolStructure).file_path || '未知'}
                      </code>
                    </div>
                    {(structure as ToolStructure).description && (
                      <div className="col-span-2">
                        <span className="text-slate">描述：</span>
                        <span className="text-ink">{(structure as ToolStructure).description}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* 参数定义 */}
                {(structure as ToolStructure).parameters.length > 0 && (
                  <div className="bg-blue-50 rounded-lg p-4">
                    <h4 className="text-sm font-semibold text-ink mb-3">输入参数</h4>
                    <div className="space-y-2">
                      {(structure as ToolStructure).parameters.map((p, i) => (
                        <div key={i} className="flex items-center gap-3 bg-white rounded px-3 py-2 border text-sm">
                          <code className="font-mono text-blue-700 font-medium">{p.name}</code>
                          <span className="text-xs px-1.5 py-0.5 bg-slate-100 rounded">{p.type}</span>
                          <span className="text-slate">{p.description}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 方法列表 */}
                {(structure as ToolStructure).methods.length > 0 && (
                  <div className="bg-purple-50 rounded-lg p-4">
                    <h4 className="text-sm font-semibold text-ink mb-3">类方法</h4>
                    <div className="space-y-1.5">
                      {(structure as ToolStructure).methods.map((m, i) => (
                        <div key={i} className="font-mono text-sm bg-white rounded px-3 py-1.5 border">
                          <span className="text-purple-600">{m.is_async ? 'async ' : ''}</span>
                          <span className="text-ink font-medium">{m.name}</span>
                          <span className="text-slate">({m.args.join(', ')})</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 创建模板 */}
                <div className="border rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-ink mb-3">创建新工具模板</h4>
                  <p className="text-xs text-slate mb-2">创建一个新工具需要以下结构：</p>
                  <CodeBlock language="python">
                    {(structure as ToolStructure).template}
                  </CodeBlock>
                </div>
              </div>
            )}

            {type === 'skill' && 'injection_method' in structure && (
              <div className="space-y-4">
                {/* 基本信息 */}
                <div className="bg-slate-50 rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
                    <Info className="w-4 h-4" />
                    技能基本信息
                  </h4>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <span className="text-slate">名称：</span>
                      <span className="font-medium text-ink">{(structure as SkillStructure).name}</span>
                    </div>
                    <div>
                      <span className="text-slate">版本：</span>
                      <code className="bg-white px-2 py-0.5 rounded border text-xs">
                        {(structure as SkillStructure).version}
                      </code>
                    </div>
                    <div>
                      <span className="text-slate">状态：</span>
                      <span className={`font-medium ${(structure as SkillStructure).enabled ? 'text-green-600' : 'text-slate'}`}>
                        {(structure as SkillStructure).enabled ? '已启用' : '已禁用'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate">注入方式：</span>
                      <code className="bg-white px-2 py-0.5 rounded border text-xs">
                        {(structure as SkillStructure).injection_method}
                      </code>
                    </div>
                    <div className="col-span-2">
                      <span className="text-slate">描述：</span>
                      <span className="text-ink">{(structure as SkillStructure).description}</span>
                    </div>
                  </div>
                </div>

                {/* 标签/关键词 */}
                {((structure as SkillStructure).tags?.length ?? 0) > 0 && (
                  <div className="bg-blue-50 rounded-lg p-4">
                    <h4 className="text-sm font-semibold text-ink mb-3">标签</h4>
                    <div className="flex flex-wrap gap-2">
                      {(structure as SkillStructure).tags.map((tag, i) => (
                        <span key={i} className="px-2.5 py-1 bg-white border rounded-full text-xs text-blue-700">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* 工作原理 */}
                <div className="bg-green-50 rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-ink mb-2">工作原理</h4>
                  <p className="text-sm text-slate">{(structure as SkillStructure).injection_description}</p>
                </div>

                {/* 创建模板 */}
                <div className="border rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-ink mb-3">创建新技能模板</h4>
                  <p className="text-xs text-slate mb-2">创建一个新技能需要以下结构：</p>
                  <CodeBlock language="json">
                    {(structure as SkillStructure).template}
                  </CodeBlock>
                </div>
              </div>
            )}
          </div>
        )}

        {!loading && !error && data && activeView === 'files' && (
          <div className="flex gap-4 flex-1 min-h-0">
            {/* File tree sidebar */}
            <div className="w-64 flex-shrink-0 border-r border-hairline pr-4 overflow-auto">
              {/* Source code preview */}
              {(data.source_code || data.source_markdown) && (
                <div className="mb-4">
                  <p className="text-xs font-medium text-slate mb-2 uppercase tracking-wider">
                    源代码
                  </p>
                  <button
                    className={`w-full text-left px-3 py-2 rounded text-sm transition-colors ${
                      !selectedFile || selectedFile.path === '__source__'
                        ? 'bg-brand-green/10 text-brand-green-dark font-medium'
                        : 'hover:bg-slate-50 text-ink'
                    }`}
                    onClick={() =>
                      setSelectedFile({
                        path: '__source__',
                        content: data.source_markdown || data.source_code || '',
                      })
                    }
                  >
                    <Code className="w-3.5 h-3.5 inline mr-1.5" />
                    {data.source_markdown ? 'source.md' : 'source.py'}
                  </button>
                </div>
              )}

              {/* Related files */}
              <p className="text-xs font-medium text-slate mb-2 uppercase tracking-wider">
                相关文件 ({data.files.length})
              </p>
              {data.files.length === 0 && (
                <p className="text-xs text-slate-400">无相关文件</p>
              )}
              <div className="space-y-0.5">
                {data.files.map((file, i) => (
                  <button
                    key={i}
                    className={`w-full text-left px-3 py-2 rounded text-sm transition-colors truncate ${
                      selectedFile?.path === file.path
                        ? 'bg-brand-green/10 text-brand-green-dark font-medium'
                        : 'hover:bg-slate-50 text-ink'
                    }`}
                    onClick={() => setSelectedFile(file)}
                  >
                    <FileText className="w-3.5 h-3.5 inline mr-1.5 flex-shrink-0" />
                    {file.path.split('/').pop()}
                    {file.content === null && (
                      <span className="ml-1 text-xs text-red-400">(读取失败)</span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Content preview */}
            <div className="flex-1 overflow-auto min-w-0">
              {selectedFile ? (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-mono text-slate bg-slate-50 px-2 py-1 rounded">
                      {selectedFile.path}
                    </p>
                  </div>
                  {selectedFile.content !== null ? (
                    <CodeBlock language={getFileLang(selectedFile.path)}>
                      {selectedFile.content}
                    </CodeBlock>
                  ) : (
                    <div className="p-8 text-center text-slate-400">
                      <p>文件内容读取失败</p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex items-center justify-center h-full text-slate-400">
                  <p>请从左侧选择一个文件查看</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="mt-6 pt-4 border-t border-hairline flex justify-end">
          <Button size="sm" onClick={onClose}>
            关闭
          </Button>
        </div>
      </Card>
    </div>
  );
}
