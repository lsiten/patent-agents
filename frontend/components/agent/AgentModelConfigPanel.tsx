'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Cpu, Image, Eye, EyeOff, Save, RotateCcw, RefreshCw, Loader2,
  CheckCircle2, AlertTriangle, Info,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { agentApi, systemApi } from '@/lib/api';
import type {
  ResolvedLLMConfig, ResolvedImageGenConfig,
  AgentLLMConfigUpdate, AgentImageGenConfigUpdate,
} from '@/types';

const LLM_PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
};

const IMG_PROVIDER_LABELS: Record<string, string> = {
  azure_aoai: 'Azure OpenAI',
  openai: 'OpenAI',
  stability: 'Stability AI',
};

const SOURCE_LABELS: Record<string, string> = {
  global: '使用全局默认',
  agent_yaml: '来自 agent yaml',
  runtime_override: '运行时自定义',
};

type Kind = 'llm' | 'image_gen';
type ResolvedAny = ResolvedLLMConfig | ResolvedImageGenConfig;

interface BaseProps {
  agentId: string;
  onSaved?: (resolved: ResolvedAny) => void;
}

interface LLMProps extends BaseProps {
  kind: 'llm';
  initial: ResolvedLLMConfig | null;
}

interface ImageGenProps extends BaseProps {
  kind: 'image_gen';
  initial: ResolvedImageGenConfig | null;
}

type Props = LLMProps | ImageGenProps;

interface DraftState {
  provider: string;
  baseUrl: string;
  apiKey: string;
  model: string;
  useDefault: boolean;
}

const emptyDraft = (): DraftState => ({
  provider: '',
  baseUrl: '',
  apiKey: '',
  model: '',
  useDefault: true,
});

export default function AgentModelConfigPanel(props: Props) {
  const { agentId, kind, initial, onSaved } = props;
  const isLLM = kind === 'llm';
  const Icon = isLLM ? Cpu : Image;
  const title = isLLM ? '文字 LLM 配置' : '生图配置';
  const providerLabels = isLLM ? LLM_PROVIDER_LABELS : IMG_PROVIDER_LABELS;
  const modelField = isLLM ? 'model' : 'model_id';
  const defaultModel = isLLM ? 'gpt-4-turbo-preview' : 'gpt-image-2';
  const { addToast } = useToast();

  const [providers, setProviders] = useState<Record<string, { configured: boolean; base_url: string; model_id: string }>>({});
  const [draft, setDraft] = useState<DraftState>(emptyDraft());
  const [revealedKey, setRevealedKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; latency_ms: number; error?: string | null } | null>(null);

  const lastInitialKeyRef = useRef<string>('');

  const loadProviders = useCallback(async () => {
    try {
      const sysConfig = await systemApi.config();
      const section = isLLM ? sysConfig.text_llm : sysConfig.image_gen;
      setProviders(section.providers);
    } catch (e) {
      addToast({ type: 'error', title: '加载供应商列表失败' });
    }
  }, [isLLM, addToast]);

  useEffect(() => {
    loadProviders();
  }, [loadProviders]);

  useEffect(() => {
    if (!initial) return;
    const resolvedModel = isLLM
      ? (initial as ResolvedLLMConfig).model
      : (initial as ResolvedImageGenConfig).model_id;
    const key = `${initial.provider}|${initial.base_url}|${resolvedModel}|${initial.is_default}`;
    if (key === lastInitialKeyRef.current) return;
    lastInitialKeyRef.current = key;
    setDraft({
      provider: initial.provider,
      baseUrl: initial.base_url,
      apiKey: '',
      model: resolvedModel,
      useDefault: initial.is_default,
    });
  }, [initial, isLLM]);

  const setField = <K extends keyof DraftState>(key: K, value: DraftState[K]) => {
    setDraft((d) => ({ ...d, [key]: value }));
  };

  const handleUseDefaultToggle = (useDefault: boolean) => {
    setDraft((d) => ({
      ...d,
      useDefault,
      ...(useDefault ? { provider: '', baseUrl: '', apiKey: '', model: '' } : {}),
    }));
  };

  const handleReset = () => {
    if (!initial) {
      setDraft(emptyDraft());
      return;
    }
    setDraft({
      provider: initial.provider,
      baseUrl: initial.base_url,
      apiKey: '',
      model: isLLM ? (initial as ResolvedLLMConfig).model : (initial as ResolvedImageGenConfig).model_id,
      useDefault: initial.is_default,
    });
    setTestResult(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setTestResult(null);
    try {
      let resolved: ResolvedAny;
      if (isLLM) {
        const body: AgentLLMConfigUpdate = draft.useDefault
          ? { use_default: true }
          : {
              provider: draft.provider || null,
              base_url: draft.baseUrl || null,
              api_key: draft.apiKey || null,
              model: draft.model || null,
            };
        resolved = await agentApi.updateLLMConfig(agentId, body);
      } else {
        const body: AgentImageGenConfigUpdate = draft.useDefault
          ? { use_default: true }
          : {
              provider: draft.provider || null,
              base_url: draft.baseUrl || null,
              api_key: draft.apiKey || null,
              model_id: draft.model || null,
            };
        resolved = await agentApi.updateImageGenConfig(agentId, body);
      }
      addToast({ type: 'success', title: '已保存' });
      onSaved?.(resolved);
      setDraft((d) => ({ ...d, apiKey: '' }));
    } catch (e) {
      addToast({ type: 'error', title: '保存失败', message: e instanceof Error ? e.message : '' });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      let result;
      if (isLLM) {
        const body: AgentLLMConfigUpdate = draft.useDefault
          ? {}
          : {
              provider: draft.provider || undefined,
              base_url: draft.baseUrl || undefined,
              api_key: draft.apiKey || undefined,
              model: draft.model || undefined,
            };
        result = await agentApi.testLLMConfig(agentId, body);
      } else {
        const body: AgentImageGenConfigUpdate = draft.useDefault
          ? {}
          : {
              provider: draft.provider || undefined,
              base_url: draft.baseUrl || undefined,
              api_key: draft.apiKey || undefined,
              model_id: draft.model || undefined,
            };
        result = await agentApi.testImageGenConfig(agentId, body);
      }
      setTestResult(result);
    } catch (e) {
      setTestResult({
        success: false,
        latency_ms: 0,
        error: e instanceof Error ? e.message : '测试请求失败',
      });
    } finally {
      setTesting(false);
    }
  };

  const sourceLabel = initial ? SOURCE_LABELS[initial.source] || initial.source : '—';
  const sourceVariant = initial?.source === 'runtime_override' ? 'purple' : 'gray';

  return (
    <Card variant="feature">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className="w-5 h-5 text-steel" />
            <CardTitle>{title}</CardTitle>
          </div>
          {initial && <Badge variant={sourceVariant}>{sourceLabel}</Badge>}
        </div>
        {initial && (
          <p className="text-body-sm text-slate mt-1">
            当前 Base URL: <span className="font-mono text-steel">{initial.base_url || '—'}</span>
            {' · '}
            当前 Key: <span className="font-mono text-steel">{initial.api_key_masked || '—'}</span>
          </p>
        )}
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-2 mb-md p-sm bg-canvas border border-hairline rounded-md">
          <input
            type="checkbox"
            id={`${kind}-use-default`}
            checked={draft.useDefault}
            onChange={(e) => handleUseDefaultToggle(e.target.checked)}
            className="rounded"
          />
          <label htmlFor={`${kind}-use-default`} className="text-body-sm text-ink cursor-pointer flex-1">
            使用全局默认配置（不覆盖）
          </label>
          {draft.useDefault && (
            <Info className="w-4 h-4 text-slate" />
          )}
        </div>

        <div className={draft.useDefault ? 'opacity-50 pointer-events-none' : 'space-y-md'}>
          <div>
            <label className="block text-body-sm-medium text-steel mb-1">供应商</label>
            <select
              value={draft.provider}
              onChange={(e) => setField('provider', e.target.value)}
              className="w-full px-3 py-2 border border-hairline rounded text-sm bg-white"
              disabled={draft.useDefault}
            >
              <option value="">（不变）</option>
              {Object.keys(providers).map((p) => (
                <option key={p} value={p}>
                  {providerLabels[p] || p}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-body-sm-medium text-steel mb-1">Base URL</label>
            <Input
              value={draft.baseUrl}
              onChange={(e) => setField('baseUrl', e.target.value)}
              placeholder="留空使用全局"
              mono
            />
          </div>

          <div>
            <label className="block text-body-sm-medium text-steel mb-1">API Key</label>
            <div className="flex items-center gap-2">
              <Input
                type={revealedKey ? 'text' : 'password'}
                value={draft.apiKey}
                onChange={(e) => setField('apiKey', e.target.value)}
                placeholder="留空则使用全局 key"
                mono
              />
              <button
                type="button"
                onClick={() => setRevealedKey((v) => !v)}
                className="text-slate hover:text-ink p-2"
                title={revealedKey ? '隐藏' : '显示'}
              >
                {revealedKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-xs text-slate mt-1">已配置时将以加密形式存储到 agent_overrides.json</p>
          </div>

          <div>
            <label className="block text-body-sm-medium text-steel mb-1">模型 ID</label>
            <Input
              value={draft.model}
              onChange={(e) => setField('model', e.target.value)}
              placeholder={defaultModel}
              mono
            />
          </div>
        </div>

        {testResult && (
          <div
            className={`mt-md p-sm border rounded-md flex items-start gap-2 ${
              testResult.success
                ? 'bg-brand-green-light/10 border-brand-green/30'
                : 'bg-accent-orange/10 border-accent-orange/30'
            }`}
          >
            {testResult.success ? (
              <CheckCircle2 className="w-4 h-4 text-brand-green mt-0.5 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-accent-orange mt-0.5 shrink-0" />
            )}
            <div className="flex-1 text-body-sm">
              <div className={testResult.success ? 'text-brand-green-dark' : 'text-accent-orange'}>
                {testResult.success ? '连通性正常' : '连通性失败'}
                {testResult.latency_ms > 0 && ` · ${testResult.latency_ms}ms`}
              </div>
              {testResult.error && (
                <div className="text-xs text-slate mt-1 font-mono break-all">{testResult.error}</div>
              )}
            </div>
          </div>
        )}

        <div className="flex items-center gap-2 mt-lg">
          <Button onClick={handleSave} disabled={saving || testing}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
            保存
          </Button>
          <Button variant="secondary" onClick={handleTest} disabled={saving || testing}>
            {testing ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <RefreshCw className="w-4 h-4 mr-1" />}
            测试连通性
          </Button>
          <Button variant="ghost" onClick={handleReset} disabled={saving || testing}>
            <RotateCcw className="w-4 h-4 mr-1" />
            重置
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
