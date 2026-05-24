'use client';

import { useCallback, useEffect, useState } from 'react';
import { X, Code, FileText, FolderOpen, RefreshCw } from 'lucide-react';
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
  const [data, setData] = useState<RelatedFilesResponse | null>(null);
  const [selectedFile, setSelectedFile] = useState<RelatedFileEntry | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = type === 'tool'
        ? await hermesApi.getRelatedFiles(agentId, itemId)
        : await hermesApi.getRelatedFiles(agentId, undefined, itemId);
      setData(result);
      if (result.files.length > 0) {
        setSelectedFile(result.files[0]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载相关文件失败');
    } finally {
      setLoading(false);
    }
  }, [agentId, type, itemId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

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
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-xl bg-brand-green/10 flex items-center justify-center">
            <FolderOpen className="w-5 h-5 text-brand-green" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-ink">
              {name} - 相关文件
            </h3>
            <p className="text-sm text-slate">
              {type === 'tool' ? '工具' : '技能'}关联的源代码文件
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

        {!loading && !error && data && (
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
