'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Settings, Cpu, Image, RefreshCw, CheckCircle2, AlertTriangle,
  Eye, EyeOff, Pencil, Save, X, Loader2,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { systemApi } from '@/lib/api';
import type { SystemConfigResponse, SystemConfigUpdateRequest, ProviderConfigResponse } from '@/types';

type EditingValues = Record<string, string>;

export default function SystemConfigPage() {
  const [config, setConfig] = useState<SystemConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [revealedKeys, setRevealedKeys] = useState<Set<string>>(new Set());
  const [draft, setDraft] = useState<EditingValues>({});

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await systemApi.config();
      setConfig(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载配置失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  // Start editing: populate draft from current config
  const startEditing = () => {
    if (!config) return;
    const vals: EditingValues = {};
    const collect = (prefix: string, providers: Record<string, ProviderConfigResponse>) => {
      for (const [p, cfg] of Object.entries(providers)) {
        vals[`${prefix}_${p}_base_url`] = cfg.base_url;
        vals[`${prefix}_${p}_model_id`] = cfg.model_id;
        vals[`${prefix}_${p}_api_key`] = '';
      }
    };
    vals['text_llm_active'] = config.text_llm.active_provider;
    vals['image_gen_active'] = config.image_gen.active_provider;
    collect('text_llm', config.text_llm.providers);
    collect('image_gen', config.image_gen.providers);
    setDraft(vals);
    setEditing(true);
    setSaveSuccess(false);
  };

  const cancelEditing = () => {
    setEditing(false);
    setDraft({});
  };

  const setDraftField = (key: string, value: string) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setSaveSuccess(false);

    // Build the diff between draft and current config
    const diff: SystemConfigUpdateRequest = {};

    // text_llm section
    const llmActive = draft['text_llm_active'];
    if (llmActive !== config.text_llm.active_provider) {
      diff.text_llm = { ...diff.text_llm, active_provider: llmActive };
    }
    for (const provider of Object.keys(config.text_llm.providers)) {
      const baseUrl = draft[`text_llm_${provider}_base_url`];
      const modelId = draft[`text_llm_${provider}_model_id`];
      const apiKey = draft[`text_llm_${provider}_api_key`];
      const cur = config.text_llm.providers[provider];
      const changed: { base_url?: string; model_id?: string; api_key?: string } = {};
      if (baseUrl !== cur.base_url && baseUrl !== undefined) changed.base_url = baseUrl;
      if (modelId !== cur.model_id && modelId !== undefined) changed.model_id = modelId;
      if (apiKey) changed.api_key = apiKey;
      if (Object.keys(changed).length > 0) {
        diff.text_llm = {
          ...diff.text_llm,
          providers: { ...(diff.text_llm?.providers || {}), [provider]: changed },
        };
      }
    }

    // image_gen section
    const imgActive = draft['image_gen_active'];
    if (imgActive !== config.image_gen.active_provider) {
      diff.image_gen = { ...diff.image_gen, active_provider: imgActive };
    }
    for (const provider of Object.keys(config.image_gen.providers)) {
      const baseUrl = draft[`image_gen_${provider}_base_url`];
      const modelId = draft[`image_gen_${provider}_model_id`];
      const apiKey = draft[`image_gen_${provider}_api_key`];
      const cur = config.image_gen.providers[provider];
      const changed: { base_url?: string; model_id?: string; api_key?: string } = {};
      if (baseUrl !== cur.base_url && baseUrl !== undefined) changed.base_url = baseUrl;
      if (modelId !== cur.model_id && modelId !== undefined) changed.model_id = modelId;
      if (apiKey) changed.api_key = apiKey;
      if (Object.keys(changed).length > 0) {
        diff.image_gen = {
          ...diff.image_gen,
          providers: { ...(diff.image_gen?.providers || {}), [provider]: changed },
        };
      }
    }

    try {
      const updated = await systemApi.updateConfig(diff);
      setConfig(updated);
      setEditing(false);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const toggleKey = (id: string) => {
    setRevealedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // ── Loading ──
  if (loading) {
    return (
      <div className="min-h-screen bg-canvas">
        <div className="container mx-auto px-md py-xxl">
          <div className="flex items-center gap-3 mb-xl">
            <Settings className="w-6 h-6 text-steel" />
            <h1 className="text-heading-3 font-semibold text-ink">系统配置</h1>
          </div>
          <div className="grid gap-lg">
            <Skeleton className="h-48 w-full rounded-lg" />
            <Skeleton className="h-48 w-full rounded-lg" />
          </div>
        </div>
      </div>
    );
  }

  // ── Error ──
  if (error && !config) {
    return (
      <div className="min-h-screen bg-canvas">
        <div className="container mx-auto px-md py-xxl">
          <div className="flex items-center gap-3 mb-xl">
            <Settings className="w-6 h-6 text-steel" />
            <h1 className="text-heading-3 font-semibold text-ink">系统配置</h1>
          </div>
          <Card variant="feature">
            <div className="flex flex-col items-center gap-4 py-xl">
              <AlertTriangle className="w-12 h-12 text-accent-orange" />
              <p className="text-body-md text-steel">{error}</p>
              <Button onClick={fetchConfig}>重试</Button>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  if (!config) return null;

  const providerLabels: Record<string, string> = {
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    azure_aoai: 'Azure OpenAI',
  };

  const ProviderSelect = ({
    section, providers, value, onChange,
  }: {
    section: string;
    providers: Record<string, ProviderConfigResponse>;
    value: string;
    onChange: (v: string) => void;
  }) => {
    if (!editing) {
      return (
        <Badge variant="purple">当前: {providerLabels[value] || value}</Badge>
      );
    }
    return (
      <select
        className="text-body-sm rounded-md border border-hairline bg-canvas px-2 py-1 text-ink font-euclid focus:outline-none focus:ring-2 focus:ring-brand-green"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {Object.keys(providers).map((p) => (
          <option key={p} value={p}>{providerLabels[p] || p}</option>
        ))}
      </select>
    );
  };

  const EditableField = ({
    id, value, placeholder, onChange, type = 'text', mono,
  }: {
    id: string;
    value: string;
    placeholder?: string;
    onChange: (v: string) => void;
    type?: string;
    mono?: boolean;
  }) => {
    if (!editing) {
      return (
        <span
          className={`text-body-sm ${mono ? 'font-mono' : ''} ${value ? 'text-steel' : 'italic text-slate'}`}
          title={value}
        >
          {value || '—'}
        </span>
      );
    }
    return (
      <Input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder || ''}
        onChange={(e) => onChange(e.target.value)}
        className="!w-full !text-body-sm !py-1 !px-2"
      />
    );
  };

  const renderSection = (
    sectionKey: 'text_llm' | 'image_gen',
    title: string,
    Icon: React.ElementType,
    data: SystemConfigResponse['text_llm'],
    fallback?: boolean,
  ) => {
    const activeKey = `${sectionKey}_active`;
    const activeProvider = editing ? draft[activeKey] || data.active_provider : data.active_provider;

    return (
      <Card key={sectionKey} variant="feature">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Icon className="w-5 h-5 text-steel" />
              <CardTitle>{title}</CardTitle>
            </div>
            <ProviderSelect
              section={sectionKey}
              providers={data.providers}
              value={activeProvider}
              onChange={(v) => setDraftField(activeKey, v)}
            />
          </div>
          {fallback !== undefined && (
            <div className="flex items-center gap-2 mt-sm">
              {fallback ? (
                <>
                  <AlertTriangle className="w-4 h-4 text-accent-orange" />
                  <span className="text-body-sm text-accent-orange">
                    未配置独立生图供应商，将回退使用文字 LLM 的 API
                  </span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4 text-brand-green" />
                  <span className="text-body-sm text-brand-green-dark">
                    已配置独立生图供应商
                  </span>
                </>
              )}
            </div>
          )}
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-hairline">
                  <th className="pb-sm text-body-sm-medium text-steel font-medium min-w-[100px]">供应商</th>
                  <th className="pb-sm text-body-sm-medium text-steel font-medium min-w-[60px]">状态</th>
                  <th className="pb-sm text-body-sm-medium text-steel font-medium min-w-[140px]">模型</th>
                  <th className="pb-sm text-body-sm-medium text-steel font-medium min-w-[200px]">Base URL</th>
                  <th className="pb-sm text-body-sm-medium text-steel font-medium min-w-[160px]">API Key</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.providers).map(([provider, cfg]) => {
                  const revealed = revealedKeys.has(`${sectionKey}_${provider}`);
                  const keyField = `${sectionKey}_${provider}_api_key`;
                  const baseUrlField = `${sectionKey}_${provider}_base_url`;
                  const modelField = `${sectionKey}_${provider}_model_id`;

                  return (
                    <tr key={provider} className="border-b border-hairline last:border-0">
                      <td className="py-md text-body-sm text-ink">
                        {providerLabels[provider] || provider}
                      </td>
                      <td className="py-md">
                        {cfg.configured ? (
                          <Badge variant="green" className="text-xs">已配置</Badge>
                        ) : (
                          <Badge variant="gray" className="text-xs">未配置</Badge>
                        )}
                      </td>
                      <td className="py-md max-w-[200px]">
                        <EditableField
                          id={modelField}
                          value={editing ? draft[modelField] || '' : cfg.model_id}
                          onChange={(v) => setDraftField(modelField, v)}
                          placeholder="model_id"
                          mono
                        />
                      </td>
                      <td className="py-md max-w-[300px]">
                        <EditableField
                          id={baseUrlField}
                          value={editing ? draft[baseUrlField] || '' : cfg.base_url}
                          onChange={(v) => setDraftField(baseUrlField, v)}
                          placeholder="https://..."
                          mono
                        />
                      </td>
                      <td className="py-md">
                        <div className="flex items-center gap-1.5">
                          <EditableField
                            id={keyField}
                            value={editing ? draft[keyField] || '' : cfg.api_key_masked}
                            onChange={(v) => setDraftField(keyField, v)}
                            placeholder={editing ? '输入新 key（留空不变）' : ''}
                            type={editing && !revealed ? 'password' : 'text'}
                            mono
                          />
                          {!editing && cfg.api_key_masked && (
                            <button
                              onClick={() => toggleKey(`${sectionKey}_${provider}`)}
                              className="text-slate hover:text-ink transition-colors shrink-0"
                              title={revealed ? '隐藏' : '显示完整 key'}
                            >
                              {revealed ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="min-h-screen bg-canvas">
      <div className="container mx-auto px-md py-xxl">
        {/* Header */}
        <div className="flex items-center justify-between mb-xl">
          <div className="flex items-center gap-3">
            <Settings className="w-6 h-6 text-steel" />
            <h1 className="text-heading-3 font-semibold text-ink">系统配置</h1>
            {saveSuccess && (
              <span className="flex items-center gap-1 text-body-sm text-brand-green-dark">
                <CheckCircle2 className="w-4 h-4" /> 已保存
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {editing ? (
              <>
                <Button size="sm" variant="ghost" onClick={cancelEditing} disabled={saving}>
                  <X className="w-4 h-4 mr-1.5" />
                  取消
                </Button>
                <Button size="sm" onClick={handleSave} disabled={saving}>
                  {saving ? (
                    <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                  ) : (
                    <Save className="w-4 h-4 mr-1.5" />
                  )}
                  {saving ? '保存中...' : '保存'}
                </Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="ghost" onClick={fetchConfig}>
                  <RefreshCw className="w-4 h-4 mr-1.5" />
                  刷新
                </Button>
                <Button size="sm" onClick={startEditing}>
                  <Pencil className="w-4 h-4 mr-1.5" />
                  编辑
                </Button>
              </>
            )}
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <Card variant="base" className="mb-lg border-accent-orange">
            <CardContent>
              <div className="flex items-center gap-2 text-accent-orange py-sm">
                <AlertTriangle className="w-4 h-4" />
                <span className="text-body-sm">{error}</span>
                <button className="text-body-sm underline ml-auto" onClick={() => setError(null)}>关闭</button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Config Sections */}
        <div className="grid gap-lg">
          {renderSection('text_llm', '文字 LLM 配置', Cpu, config.text_llm)}
          {renderSection('image_gen', '图片生成配置', Image, config.image_gen, config.image_gen_fallback_to_llm)}
        </div>

        {/* Env Hint */}
        <Card variant="base" className="mt-lg">
          <CardContent>
            <div className="flex items-start gap-3 py-sm">
              <AlertTriangle className="w-5 h-5 text-accent-orange shrink-0 mt-0.5" />
              <div className="text-body-sm text-steel">
                <p className="font-medium text-ink mb-1">配置方式</p>
                <p>
                  修改将立即写入 <code className="bg-surface px-1.5 py-0.5 rounded text-xs font-mono">backend/.env</code> 文件。
                  部分配置项（如 base_url）需要重启后端服务才能生效。
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
