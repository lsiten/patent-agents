'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Settings,
  Wrench,
  Sparkles,
  Clock,
  Database,
  FolderOpen,
  ChevronRight,
  Plus,
  Trash2,
  Edit,
  ToggleLeft,
  ToggleRight,
  Save,
  X,
  Bot,
  AlertCircle,
  RefreshCw,
  Code,
  Eye,
  FileText,
  Search,
  Upload,
  Wand2,
  Info,
  Cpu,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Skeleton, AgentCardSkeleton } from '@/components/ui/Skeleton';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs';
import { Textarea } from '@/components/ui/Textarea';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { agentApi, hermesApi } from '@/lib/api';
import { CodeBlock } from '@/components/ui/CodeBlock';
import AgentModelConfigPanel from '@/components/agent/AgentModelConfigPanel';
import RelatedDetailModal from '@/components/RelatedDetailModal';
import HermesToolChatModal from '@/components/HermesToolChatModal';
import HermesSkillChatModal from '@/components/HermesSkillChatModal';
import SkillUploadModal from '@/components/SkillUploadModal';
import type { AgentConfig, AgentTool, AgentSkill, AgentTimer, AgentMemory, MemoryEntry, DirEntry } from '@/types';

/** Parse a 5-field cron expression into its parts */
function parseCron(expr: string): { minute: string; hour: string; day: string; month: string; weekday: string } {
  const parts = expr.split(/\s+/);
  return {
    minute: parts[0] || '*',
    hour: parts[1] || '*',
    day: parts[2] || '*',
    month: parts[3] || '*',
    weekday: parts[4] || '*',
  };
}

/** Build a 5-field cron expression from its parts */
function buildCron(minute: string, hour: string, day: string, month: string, weekday: string): string {
  return `${minute} ${hour} ${day} ${month} ${weekday}`;
}

/** Generate options for a cron field: [{value, label}, ...] */
function rangeOptions(from: number, to: number, pad = false): { value: string; label: string }[] {
  return Array.from({ length: to - from + 1 }, (_, i) => {
    const v = pad ? String(i + from).padStart(2, '0') : String(i + from);
    return { value: v, label: v };
  });
}
const minuteOptions = rangeOptions(0, 59, true);
const hourOptions = rangeOptions(0, 23, true);
const dayOptions = rangeOptions(1, 31);
const monthOptions = rangeOptions(1, 12);
const weekdayOptions = [
  { value: '0', label: '日' }, { value: '1', label: '一' }, { value: '2', label: '二' },
  { value: '3', label: '三' }, { value: '4', label: '四' }, { value: '5', label: '五' }, { value: '6', label: '六' },
];

/** A small select element for one cron field */
function CronSelect({ label, value, onChange, options, children }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options?: { value: string; label: string }[];
  children?: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs text-slate mb-1">{label}</label>
      <select
        className="w-full px-2 py-2 border rounded text-sm bg-white"
        value={value}
        onChange={e => onChange(e.target.value)}
      >
        <option value="*">任意</option>
        {options
          ? options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)
          : children}
      </select>
    </div>
  );
}

const roleLabels: Record<string, string> = {
  orchestrator: '统筹者',
  specialist: '专业Agent',
  assistant: '助手',
  critic: '评审',
};

const roleColors: Record<string, string> = {
  orchestrator: 'bg-purple-100 text-purple-700',
  specialist: 'bg-blue-100 text-blue-700',
  assistant: 'bg-green-100 text-green-700',
  critic: 'bg-orange-100 text-orange-700',
};

const categoryColors: Record<string, string> = {
  search: 'bg-blue-100 text-blue-700',
  file: 'bg-green-100 text-green-700',
  analysis: 'bg-purple-100 text-purple-700',
  external: 'bg-orange-100 text-orange-700',
};

const memoryTypeLabels: Record<string, string> = {
  short_term: '短期记忆',
  long_term: '长期记忆',
  knowledge_base: '知识库',
};

const memoryTypeColors: Record<string, string> = {
  short_term: 'bg-blue-100 text-blue-700',
  long_term: 'bg-purple-100 text-purple-700',
  knowledge_base: 'bg-green-100 text-green-700',
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
  return (bytes / 1073741824).toFixed(1) + ' GB';
}

export default function AgentsPage() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('tools');
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [tools, setTools] = useState<Record<string, AgentTool[]>>({});
  const [skills, setSkills] = useState<Record<string, AgentSkill[]>>({});
  const [timers, setTimers] = useState<Record<string, AgentTimer[]>>({});
  const [memories, setMemories] = useState<Record<string, AgentMemory[]>>({});
  const [modelConfigs, setModelConfigs] = useState<Record<string, { llm: any; image_gen: any }>>({});
  const [editingConfig, setEditingConfig] = useState(false);
  const [editForm, setEditForm] = useState<Partial<AgentConfig>>({});
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoadingAgents, setIsLoadingAgents] = useState(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Add/edit/delete state
  const [editingToolId, setEditingToolId] = useState<string | null>(null);
  const [editingSkillId, setEditingSkillId] = useState<string | null>(null);
  const [editingTimerId, setEditingTimerId] = useState<string | null>(null);
  const [editToolForm, setEditToolForm] = useState<Partial<AgentTool>>({});
  const [editSkillForm, setEditSkillForm] = useState<Partial<AgentSkill>>({});
  const [editTimerForm, setEditTimerForm] = useState<Partial<AgentTimer>>({});
  const [showAddTool, setShowAddTool] = useState(false);
  const [showAddSkill, setShowAddSkill] = useState(false);
  const [showAddTimer, setShowAddTimer] = useState(false);
  const [newToolForm, setNewToolForm] = useState({ name: '', description: '', category: 'search' as AgentTool['category'] });
  const [newSkillForm, setNewSkillForm] = useState({ name: '', description: '', tags: '' });
  const [newTimerForm, setNewTimerForm] = useState({ name: '', cron_expression: '0 * * * *', action: '' });
  // Cron field parts for add form
  const [newCron, setNewCron] = useState({ minute: '0', hour: '*', day: '*', month: '*', weekday: '*' });
  // Cron field parts for edit form
  const [editCron, setEditCron] = useState({ minute: '*', hour: '*', day: '*', month: '*', weekday: '*' });
  const [viewMemory, setViewMemory] = useState<AgentMemory | null>(null);
  const [viewToolSource, setViewToolSource] = useState<AgentTool | null>(null);
  const [viewMemoryEntry, setViewMemoryEntry] = useState<MemoryEntry | null>(null);
  const [showHermesChat, setShowHermesChat] = useState(false);
  const [showHermesSkillChat, setShowHermesSkillChat] = useState(false);
  const [showRelatedDetail, setShowRelatedDetail] = useState<{
    open: boolean;
    type: 'tool' | 'skill';
    itemId: string;
    name: string;
  } | null>(null);
  const [showSkillUpload, setShowSkillUpload] = useState(false);
  const [viewSystemPrompt, setViewSystemPrompt] = useState(false);
  const [browseEntries, setBrowseEntries] = useState<DirEntry[] | null>(null);
  const [browseCurrentPath, setBrowseCurrentPath] = useState('');
  const [browsePathStack, setBrowsePathStack] = useState<string[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [fileContent, setFileContent] = useState<{path: string; content: string} | null>(null);
  const [isLoadingFileContent, setIsLoadingFileContent] = useState(false);
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
  }>({ open: false, title: '', message: '', onConfirm: () => {} });

  const currentAgent = selectedAgent ? agents.find(a => a.id === selectedAgent) : undefined;
  const currentTools = selectedAgent ? tools[selectedAgent] || [] : [];
  const currentSkills = selectedAgent ? skills[selectedAgent] || [] : [];
  const currentTimers = selectedAgent ? timers[selectedAgent] || [] : [];
  const currentMemories = selectedAgent ? memories[selectedAgent] || [] : [];

  const filteredAgents = agents.filter(agent =>
    agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    agent.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const loadAgentList = useCallback(async (showLoading = false) => {
    if (showLoading) {
      setIsLoadingAgents(true);
    } else {
      setIsRefreshing(true);
    }

    try {
      const response = await agentApi.list();
      setAgents(response.agents);
      setSelectedAgent((current) => current ?? response.agents[0]?.id ?? null);
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '获取Agent列表失败');
    } finally {
      setIsLoadingAgents(false);
      setIsRefreshing(false);
    }
  }, []);

  const loadAgentDetail = useCallback(async (agentId: string) => {
    setIsLoadingDetail(true);
    try {
      const detail = await agentApi.get(agentId);
      setAgents((currentAgents) => currentAgents.map((agent) =>
        agent.id === agentId ? detail.config : agent
      ));
      setTools((currentToolsByAgent) => ({ ...currentToolsByAgent, [agentId]: detail.tools }));
      setSkills((currentSkillsByAgent) => ({ ...currentSkillsByAgent, [agentId]: detail.skills }));
      setTimers((currentTimersByAgent) => ({ ...currentTimersByAgent, [agentId]: detail.timers }));
      setMemories((currentMemoriesByAgent) => ({ ...currentMemoriesByAgent, [agentId]: detail.memories }));
      setModelConfigs((prev) => ({
        ...prev,
        [agentId]: {
          llm: (detail as any).llm_config ?? null,
          image_gen: (detail as any).image_gen_config ?? null,
        },
      }));
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '获取Agent详情失败');
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    void loadAgentList(true);
  }, [loadAgentList]);

  useEffect(() => {
    if (!selectedAgent) return;
    void loadAgentDetail(selectedAgent);
  }, [loadAgentDetail, selectedAgent]);

  const toggleTool = (toolId: string) => {
    if (!selectedAgent) return;
    const tool = currentTools.find((item) => item.id === toolId);
    if (!tool) return;
    const nextEnabled = !tool.enabled;

    const actionKey = `tool:${selectedAgent}:${toolId}`;
    setPendingAction(actionKey);

    agentApi.toggleTool(selectedAgent, toolId, nextEnabled)
      .then(() => {
        setTools(prev => ({
          ...prev,
          [selectedAgent]: (prev[selectedAgent] || []).map(t =>
            t.id === toolId ? { ...t, enabled: nextEnabled } : t
          ),
        }));
      })
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '更新工具状态失败');
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };

  const toggleSkill = (skillId: string) => {
    if (!selectedAgent) return;
    const skill = currentSkills.find((item) => item.id === skillId);
    if (!skill) return;
    const nextEnabled = !skill.enabled;

    const actionKey = `skill:${selectedAgent}:${skillId}`;
    setPendingAction(actionKey);

    agentApi.toggleSkill(selectedAgent, skillId, nextEnabled)
      .then(() => {
        setSkills(prev => ({
          ...prev,
          [selectedAgent]: (prev[selectedAgent] || []).map(s =>
            s.id === skillId ? { ...s, enabled: nextEnabled } : s
          ),
        }));
      })
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '更新技能状态失败');
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };

  const toggleTimer = (timerId: string) => {
    if (!selectedAgent) return;
    const timer = currentTimers.find((item) => item.id === timerId);
    if (!timer) return;
    const nextEnabled = !timer.enabled;

    const actionKey = `timer:${selectedAgent}:${timerId}`;
    setPendingAction(actionKey);

    agentApi.toggleTimer(selectedAgent, timerId, nextEnabled)
      .then(() => {
        setTimers(prev => ({
          ...prev,
          [selectedAgent]: (prev[selectedAgent] || []).map(t =>
            t.id === timerId ? { ...t, enabled: nextEnabled } : t
          ),
        }));
      })
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '更新定时器状态失败');
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };

  const toggleAgentEnabled = (agentId: string) => {
    const agent = agents.find((item) => item.id === agentId);
    if (!agent) return;
    const nextEnabled = !agent.enabled;

    const actionKey = `agent:${agentId}`;
    setPendingAction(actionKey);

    agentApi.update(agentId, { enabled: nextEnabled })
      .then(() => {
        setAgents(prev => prev.map(a =>
          a.id === agentId ? { ...a, enabled: nextEnabled } : a
        ));
      })
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '更新Agent状态失败');
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };

  const startEditConfig = () => {
    if (currentAgent) {
      setEditForm(currentAgent);
      setEditingConfig(true);
    }
  };

  const saveConfig = () => {
    if (!selectedAgent || !currentAgent) return;
    const updatedAgent = { ...currentAgent, ...editForm, updated_at: new Date().toISOString() };

    const actionKey = `config:${selectedAgent}`;
    setPendingAction(actionKey);

    agentApi.update(selectedAgent, editForm)
      .then(() => {
        setAgents(prev => prev.map(a =>
          a.id === selectedAgent ? updatedAgent : a
        ));
        setEditingConfig(false);
      })
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '保存Agent配置失败');
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };

  const clearMemory = (memoryId: string) => {
    if (!selectedAgent) return;
    const memory = currentMemories.find((item) => item.id === memoryId);
    if (!memory) return;

    const actionKey = `memory:${selectedAgent}:${memoryId}`;
    setPendingAction(actionKey);

    agentApi.clearMemory(selectedAgent, memoryId)
      .then(() => {
        setMemories(prev => ({
          ...prev,
          [selectedAgent]: (prev[selectedAgent] || []).map(m =>
            m.id === memoryId ? { ...m, size: 0, item_count: 0, last_updated: new Date().toISOString() } : m
          ),
        }));
      })
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '清空Agent记忆失败');
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };

  const deleteMemoryEntry = (memoryId: string, entryId: string) => {
    if (!selectedAgent) return;
    const actionKey = `memory_entry:${selectedAgent}:${memoryId}:${entryId}`;
    setPendingAction(actionKey);
    agentApi.deleteMemoryEntry(selectedAgent, memoryId, entryId)
      .then(() => {
        setMemories(prev => {
          const agentMemories = (prev[selectedAgent] || []).map(m => {
            if (m.id !== memoryId) return m;
            return {
              ...m,
              entries: (m.entries || []).filter(e => e.id !== entryId),
              item_count: Math.max(0, m.item_count - 1),
            };
          });
          return { ...prev, [selectedAgent]: agentMemories };
        });
        setViewMemory(prev => {
          if (!prev || prev.id !== memoryId) return prev;
          return {
            ...prev,
            entries: (prev.entries || []).filter(e => e.id !== entryId),
            item_count: Math.max(0, prev.item_count - 1),
          };
        });
      })
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '删除记忆条目失败');
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };

  const browseWorkingDir = async () => {
    if (!selectedAgent || !currentAgent?.working_directory) return;
    setIsLoadingFiles(true);
    setBrowsePathStack([]);
    try {
      const result = await agentApi.browseDirectory(selectedAgent, '');
      setBrowseEntries(result.entries);
      setBrowseCurrentPath(result.path);
    } catch (err) {
      setError(err instanceof Error ? err.message : '浏览目录失败');
      setBrowseEntries([]);
    } finally {
      setIsLoadingFiles(false);
    }
  };

  const navigateToDir = async (dirPath: string) => {
    if (!selectedAgent) return;
    setIsLoadingFiles(true);
    setBrowsePathStack(prev => [...prev, browseCurrentPath]);
    try {
      const result = await agentApi.browseDirectory(selectedAgent, dirPath);
      setBrowseEntries(result.entries);
      setBrowseCurrentPath(result.path);
    } catch (err) {
      setError(err instanceof Error ? err.message : '浏览目录失败');
    } finally {
      setIsLoadingFiles(false);
    }
  };

  const navigateUp = async () => {
    if (!selectedAgent || browsePathStack.length === 0) return;
    setIsLoadingFiles(true);
    const prevPath = browsePathStack[browsePathStack.length - 1];
    setBrowsePathStack(prev => prev.slice(0, -1));
    try {
      const result = await agentApi.browseDirectory(selectedAgent, prevPath === '/' ? '' : prevPath);
      setBrowseEntries(result.entries);
      setBrowseCurrentPath(result.path);
    } catch (err) {
      setError(err instanceof Error ? err.message : '返回上级目录失败');
    } finally {
      setIsLoadingFiles(false);
    }
  };

  const openFileContent = async (filePath: string) => {
    if (!selectedAgent) return;
    setIsLoadingFileContent(true);
    try {
      const result = await agentApi.getAgentFileContent(selectedAgent, filePath);
      setFileContent(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '读取文件失败');
      setFileContent(null);
    } finally {
      setIsLoadingFileContent(false);
    }
  };

  function formatBytes(bytes?: number): string {
    if (bytes === undefined || bytes === null) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  // Tool/Skill/Timer CRUD handlers
  const startEditTool = (tool: AgentTool) => {
    setEditingToolId(tool.id);
    setEditToolForm({ ...tool });
  };
  const cancelEditTool = () => { setEditingToolId(null); setEditToolForm({}); };
  const saveEditTool = () => {
    if (!selectedAgent || !editingToolId) return;
    const actionKey = `edit_tool:${selectedAgent}:${editingToolId}`;
    setPendingAction(actionKey);
    const updated = currentTools.map(t => t.id === editingToolId ? { ...t, ...editToolForm } as AgentTool : t);
    setTools(prev => ({ ...prev, [selectedAgent]: updated }));
    setEditingToolId(null);
    setEditToolForm({});
    agentApi.updateTools(selectedAgent, updated)
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '保存工具失败');
        void loadAgentDetail(selectedAgent);
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };
  const deleteTool = (toolId: string) => {
    if (!selectedAgent) return;
    setConfirmDialog({
      open: true,
      title: '删除工具',
      message: '确定要删除此工具吗？',
      onConfirm: () => {
        setConfirmDialog(prev => ({ ...prev, open: false }));
    const actionKey = `delete_tool:${selectedAgent}:${toolId}`;
    setPendingAction(actionKey);
    const updated = (tools[selectedAgent] || []).filter(t => t.id !== toolId);
    setTools(prev => ({ ...prev, [selectedAgent]: updated }));
    agentApi.updateTools(selectedAgent, updated)
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '删除工具失败');
        void loadAgentDetail(selectedAgent);
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
      },
    });
  };

  const startEditSkill = (skill: AgentSkill) => {
    setEditingSkillId(skill.id);
    setEditSkillForm({ ...skill });
  };
  const cancelEditSkill = () => { setEditingSkillId(null); setEditSkillForm({}); };
  const saveEditSkill = () => {
    if (!selectedAgent || !editingSkillId) return;
    const actionKey = `edit_skill:${selectedAgent}:${editingSkillId}`;
    setPendingAction(actionKey);
    const updated = currentSkills.map(s => s.id === editingSkillId ? { ...s, ...editSkillForm } as AgentSkill : s);
    setSkills(prev => ({ ...prev, [selectedAgent]: updated }));
    setEditingSkillId(null);
    setEditSkillForm({});
    agentApi.updateSkills(selectedAgent, updated)
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '保存技能失败');
        void loadAgentDetail(selectedAgent);
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };
  const deleteSkill = (skillId: string) => {
    if (!selectedAgent) return;
    setConfirmDialog({
      open: true,
      title: '删除技能',
      message: '确定要删除此技能吗？',
      onConfirm: () => {
        setConfirmDialog(prev => ({ ...prev, open: false }));
    const actionKey = `delete_skill:${selectedAgent}:${skillId}`;
    setPendingAction(actionKey);
    const updated = (skills[selectedAgent] || []).filter(s => s.id !== skillId);
    setSkills(prev => ({ ...prev, [selectedAgent]: updated }));
    agentApi.updateSkills(selectedAgent, updated)
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '删除技能失败');
        void loadAgentDetail(selectedAgent);
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
      },
    });
  };

  const startEditTimer = (timer: AgentTimer) => {
    setEditingTimerId(timer.id);
    setEditTimerForm({ ...timer });
    const parts = parseCron(timer.cron_expression || '');
    setEditCron({ minute: parts.minute, hour: parts.hour, day: parts.day, month: parts.month, weekday: parts.weekday });
  };
  const cancelEditTimer = () => { setEditingTimerId(null); setEditTimerForm({}); setEditCron({ minute: '*', hour: '*', day: '*', month: '*', weekday: '*' }); };
  const saveEditTimer = () => {
    if (!selectedAgent || !editingTimerId) return;
    const actionKey = `edit_timer:${selectedAgent}:${editingTimerId}`;
    setPendingAction(actionKey);
    const editCronExpr = buildCron(editCron.minute, editCron.hour, editCron.day, editCron.month, editCron.weekday);
    const updatedTimer = { ...editTimerForm, cron_expression: editCronExpr } as AgentTimer;
    const updated = currentTimers.map(t => t.id === editingTimerId ? { ...t, ...updatedTimer } : t);
    setTimers(prev => ({ ...prev, [selectedAgent]: updated }));
    setEditingTimerId(null);
    setEditTimerForm({});
    agentApi.updateTimers(selectedAgent, updated)
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '保存定时器失败');
        void loadAgentDetail(selectedAgent);
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };
  const deleteTimer = (timerId: string) => {
    if (!selectedAgent) return;
    setConfirmDialog({
      open: true,
      title: '删除定时器',
      message: '确定要删除此定时器吗？',
      onConfirm: () => {
        setConfirmDialog(prev => ({ ...prev, open: false }));
    const actionKey = `delete_timer:${selectedAgent}:${timerId}`;
    setPendingAction(actionKey);
    const updated = (timers[selectedAgent] || []).filter(t => t.id !== timerId);
    setTimers(prev => ({ ...prev, [selectedAgent]: updated }));
    agentApi.updateTimers(selectedAgent, updated)
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '删除定时器失败');
        void loadAgentDetail(selectedAgent);
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
      },
    });
  };

  const addTool = () => {
    if (!selectedAgent) return;
    const actionKey = `add_tool:${selectedAgent}`;
    setPendingAction(actionKey);
    const newTool: AgentTool = { id: `tool_${Date.now()}`, ...newToolForm, enabled: true };
    const updated = [...(tools[selectedAgent] || []), newTool];
    setTools(prev => ({ ...prev, [selectedAgent]: updated }));
    setShowAddTool(false);
    setNewToolForm({ name: '', description: '', category: 'search' });
    agentApi.updateTools(selectedAgent, updated)
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '添加工具失败');
        void loadAgentDetail(selectedAgent);
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };
  const addSkill = () => {
    if (!selectedAgent) return;
    const actionKey = `add_skill:${selectedAgent}`;
    setPendingAction(actionKey);
    const newSkill: AgentSkill = {
      id: `skill_${Date.now()}`, name: newSkillForm.name, description: newSkillForm.description,
      tags: newSkillForm.tags ? newSkillForm.tags.split(',').map(t => t.trim()) : [], version: '1.0.0', enabled: true,
    };
    const updated = [...(skills[selectedAgent] || []), newSkill];
    setSkills(prev => ({ ...prev, [selectedAgent]: updated }));
    setShowAddSkill(false);
    setNewSkillForm({ name: '', description: '', tags: '' });
    agentApi.updateSkills(selectedAgent, updated)
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '添加技能失败');
        void loadAgentDetail(selectedAgent);
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };
  const addTimer = () => {
    if (!selectedAgent) return;
    const actionKey = `add_timer:${selectedAgent}`;
    setPendingAction(actionKey);
    const cronExpr = buildCron(newCron.minute, newCron.hour, newCron.day, newCron.month, newCron.weekday);
    const newTimer: AgentTimer = { id: `timer_${Date.now()}`, name: newTimerForm.name, cron_expression: cronExpr, action: newTimerForm.action, enabled: true };
    const updated = [...(timers[selectedAgent] || []), newTimer];
    setTimers(prev => ({ ...prev, [selectedAgent]: updated }));
    setShowAddTimer(false);
    setNewTimerForm({ name: '', cron_expression: '0 * * * *', action: '' });
    setNewCron({ minute: '0', hour: '*', day: '*', month: '*', weekday: '*' });
    agentApi.updateTimers(selectedAgent, updated)
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '添加定时器失败');
        void loadAgentDetail(selectedAgent);
      })
      .finally(() => setPendingAction((current) => current === actionKey ? null : current));
  };

  if (isLoadingAgents) {
    return (
      <div className="min-h-screen bg-surface">
        <div className="max-w-7xl mx-auto p-6">
          <div className="mb-6">
            <Skeleton className="h-8 w-48 mb-2" />
            <Skeleton className="h-4 w-72" />
          </div>
          <div className="flex gap-6">
            <div className="w-80 flex-shrink-0 space-y-3">
              <Skeleton className="h-10 w-full rounded-lg" />
              {Array.from({ length: 3 }).map((_, i) => (
                <AgentCardSkeleton key={i} />
              ))}
            </div>
            <div className="flex-1">
              <Card className="p-6">
                <div className="flex items-center gap-4 mb-6">
                  <Skeleton className="w-12 h-12 rounded-xl" />
                  <div className="flex-1">
                    <Skeleton className="h-6 w-40 mb-2" />
                    <Skeleton className="h-4 w-56" />
                  </div>
                </div>
                <Skeleton className="h-10 w-full rounded-lg mb-6" />
                <div className="space-y-4">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-4 w-5/6" />
                </div>
              </Card>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!currentAgent) {
    return (
      <div className="min-h-screen bg-surface p-6">
        <Card className="p-12 text-center">
          <Bot className="w-12 h-12 text-slate-400 mx-auto mb-4" />
          <p className="text-slate-500">请选择一个Agent进行管理</p>
          {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
          <Button className="mt-4" onClick={() => {
            loadAgentList(false).catch((requestError) => {
              setError(requestError instanceof Error ? requestError.message : '获取Agent列表失败');
            });
          }} disabled={isRefreshing}>
            <RefreshCw className={`w-4 h-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            重新加载
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <>
    <div className="min-h-screen bg-surface">
      <div className="max-w-7xl mx-auto p-6">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-ink">Agent管理</h1>
              <p className="text-sm text-slate mt-1">
                管理多智能体系统中的所有Agent配置、工具、技能与资源
              </p>
            </div>
            <Button variant="secondary" onClick={() => {
              loadAgentList(false).catch((requestError) => {
                setError(requestError instanceof Error ? requestError.message : '获取Agent列表失败');
              });
            }} disabled={isRefreshing}>
              <RefreshCw className={`w-4 h-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
              刷新
            </Button>
          </div>
        </div>

        {error && (
          <Card className="p-4 mb-5 border-red-200 bg-red-50">
            <div className="flex items-center gap-2 text-red-700">
              <AlertCircle className="w-5 h-5" />
              <span className="text-sm font-medium">{error}</span>
            </div>
          </Card>
        )}

        <div className="flex gap-6">
          {/* Agent List Sidebar */}
          <div className="w-80 flex-shrink-0">
            <Card className="p-4">
              <div className="mb-4">
                <Input
                  placeholder="搜索Agent..."
                  icon={<Settings className="w-4 h-4" />}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                {filteredAgents.map((agent) => (
                  <div
                    key={agent.id}
                    onClick={() => setSelectedAgent(agent.id)}
                    className={`p-4 rounded-lg cursor-pointer transition-all ${
                      selectedAgent === agent.id
                        ? 'bg-brand-green/10 ring-2 ring-brand-green'
                        : 'bg-white hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-medium text-ink truncate">{agent.name}</h3>
                          <Badge
                            variant="soft"
                            className={agent.enabled ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'}
                          >
                            {agent.enabled ? '运行中' : '已停用'}
                          </Badge>
                        </div>
                        <p className="text-xs text-slate truncate mb-2">{agent.description}</p>
                        <div className="flex items-center gap-2">
                          <Badge variant="soft" className={roleColors[agent.role]}>
                            {roleLabels[agent.role]}
                          </Badge>
                          <span className="text-xs text-slate">{agent.model.split('-').slice(0, 2).join('-')}</span>
                        </div>
                      </div>
                      <ChevronRight className="w-5 h-5 text-slate-400 flex-shrink-0 ml-2" />
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* Main Content */}
          <div className="flex-1">
            {isLoadingDetail && (
              <Card className="p-4 mb-6">
                <div className="flex items-center gap-2 text-slate">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span className="text-sm">正在同步 Agent 详情...</span>
                </div>
              </Card>
            )}

            {/* Agent Header */}
            <Card className="p-6 mb-6">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-3 mb-2">
                    <div className="w-12 h-12 rounded-xl bg-brand-green/20 flex items-center justify-center">
                      <Bot className="w-6 h-6 text-brand-green-dark" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-xl font-semibold text-ink">{currentAgent.name}</h2>
                        <Badge variant="soft" className={roleColors[currentAgent.role]}>
                          {roleLabels[currentAgent.role]}
                        </Badge>
                      </div>
                      <p className="text-sm text-slate">{currentAgent.description}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 mt-4 text-sm text-slate">
                    <span>模型: <code className="bg-slate-100 px-2 py-0.5 rounded">{currentAgent.model}</code></span>
                    <span>Temperature: {currentAgent.temperature}</span>
                    <span>Max Tokens: {currentAgent.max_tokens}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => toggleAgentEnabled(currentAgent.id)}
                    disabled={pendingAction === `agent:${currentAgent.id}`}
                  >
                    {currentAgent.enabled ? (
                      <><ToggleRight className="w-4 h-4 mr-1 text-green-500" /> 停用</>
                    ) : (
                      <><ToggleLeft className="w-4 h-4 mr-1 text-slate-400" /> 启用</>
                    )}
                  </Button>
                </div>
              </div>
            </Card>

            {/* Tabs */}
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="mb-6">
                <TabsTrigger value="tools">
                  <Wrench className="w-4 h-4 mr-2" />
                  工具管理
                </TabsTrigger>
                <TabsTrigger value="skills">
                  <Sparkles className="w-4 h-4 mr-2" />
                  技能管理
                </TabsTrigger>
                <TabsTrigger value="timers">
                  <Clock className="w-4 h-4 mr-2" />
                  定时器
                </TabsTrigger>
                <TabsTrigger value="memory">
                  <Database className="w-4 h-4 mr-2" />
                  记忆管理
                </TabsTrigger>
                <TabsTrigger value="config">
                  <Settings className="w-4 h-4 mr-2" />
                  配置
                </TabsTrigger>
                <TabsTrigger value="model-config">
                  <Cpu className="w-4 h-4 mr-2" />
                  模型配置
                </TabsTrigger>
              </TabsList>

              {/* Tools Tab */}
              <TabsContent value="tools">
                <Card className="p-6">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <h3 className="text-lg font-semibold text-ink">工具列表</h3>
                      <p className="text-sm text-slate mt-1">管理此Agent可用的工具集</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="secondary" onClick={() => setShowHermesChat(true)}>
                        <Wand2 className="w-4 h-4 mr-1" />
                        Hermes 生成
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-4">
                      {currentTools.map((tool) => (
                        <div
                          key={tool.id}
                          className="p-4 bg-white rounded-lg border border-hairline"
                        >
                          {editingToolId === tool.id ? (
                            <div className="space-y-3">
                              <h4 className="font-medium text-ink">编辑工具</h4>
                              <input
                                className="w-full px-3 py-2 border rounded text-sm"
                                placeholder="工具名称"
                                value={editToolForm.name || ''}
                                onChange={e => setEditToolForm(f => ({ ...f, name: e.target.value }))}
                              />
                              <input
                                className="w-full px-3 py-2 border rounded text-sm"
                                placeholder="工具描述"
                                value={editToolForm.description || ''}
                                onChange={e => setEditToolForm(f => ({ ...f, description: e.target.value }))}
                              />
                              <select
                                className="w-full px-3 py-2 border rounded text-sm"
                                value={editToolForm.category || 'search'}
                                onChange={e => setEditToolForm(f => ({ ...f, category: e.target.value as AgentTool['category'] }))}
                              >
                                <option value="search">Search</option>
                                <option value="file">File</option>
                                <option value="analysis">Analysis</option>
                                <option value="external">External</option>
                              </select>
                              <div className="flex gap-2">
                                <Button size="sm" onClick={saveEditTool}>
                                  <Save className="w-4 h-4 mr-1" />
                                  保存
                                </Button>
                                <Button variant="ghost" size="sm" onClick={cancelEditTool}>
                                  <X className="w-4 h-4 mr-1" />
                                  取消
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <div className="flex items-center gap-2 mb-1">
                                  <h4 className="font-medium text-ink">{tool.name}</h4>
                                  <Badge variant="soft" className={categoryColors[tool.category]}>
                                    {tool.category}
                                  </Badge>
                                </div>
                                <p className="text-sm text-slate">{tool.description}</p>
                              </div>
                              <div className="flex items-center gap-2 ml-4">
                                {tool.source_code && (
                                  <Button variant="ghost" size="sm" onClick={() => setViewToolSource(tool)}>
                                    <Code className="w-4 h-4 mr-1" />
                                    查看代码
                                  </Button>
                                )}
                                {selectedAgent && (
                                  <Button variant="ghost" size="sm" onClick={() => setShowRelatedDetail({
                                    open: true,
                                    type: 'tool',
                                    itemId: tool.id,
                                    name: tool.name,
                                  })}>
                                    <Info className="w-4 h-4 mr-1" />
                                    详情
                                  </Button>
                                )}
                                {tool.is_hermes && (
                                  <Badge variant="soft" className="bg-cyan-100 text-cyan-700 text-xs">Hermes</Badge>
                                )}
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => toggleTool(tool.id)}
                                  disabled={pendingAction === `tool:${selectedAgent}:${tool.id}`}
                                >
                                  {tool.enabled ? (
                                    <><ToggleRight className="w-5 h-5 text-green-500" /></>
                                  ) : (
                                    <><ToggleLeft className="w-5 h-5 text-slate-400" /></>
                                  )}
                                </Button>
                                <Button variant="ghost" size="sm" onClick={() => startEditTool(tool)}>
                                  <Edit className="w-4 h-4" />
                                </Button>
                                <Button variant="ghost" size="sm" onClick={() => deleteTool(tool.id)}>
                                  <Trash2 className="w-4 h-4 text-red-500" />
                                </Button>
                              </div>
                            </div>
                          )}
                        </div>
                    ))}
                  </div>
                </Card>
              </TabsContent>

              {/* Skills Tab */}
              <TabsContent value="skills">
                <Card className="p-6">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <h3 className="text-lg font-semibold text-ink">技能列表</h3>
                      <p className="text-sm text-slate mt-1">管理此Agent的专业技能与版本</p>
                    </div>
<div className="flex items-center gap-2">
                       <Button size="sm" variant="secondary" onClick={() => setShowSkillUpload(true)}>
                         <Upload className="w-4 h-4 mr-1" />
                         上传技能包
                       </Button>
                        <Button size="sm" onClick={() => setShowHermesSkillChat(true)}>
                         <Sparkles className="w-4 h-4 mr-1" />
                         聊天生成
                       </Button>
                     </div>
                  </div>
                  <div className="space-y-4">
                    {currentSkills.map((skill) => (
                      <div
                        key={skill.id}
                        className="p-4 bg-white rounded-lg border border-hairline"
                      >
                        {editingSkillId === skill.id ? (
                          <div className="space-y-3">
                            <h4 className="font-medium text-ink">编辑技能</h4>
                            <input
                              className="w-full px-3 py-2 border rounded text-sm"
                              placeholder="技能名称"
                              value={editSkillForm.name || ''}
                              onChange={e => setEditSkillForm(f => ({ ...f, name: e.target.value }))}
                            />
                            <input
                              className="w-full px-3 py-2 border rounded text-sm"
                              placeholder="技能描述"
                              value={editSkillForm.description || ''}
                              onChange={e => setEditSkillForm(f => ({ ...f, description: e.target.value }))}
                            />
                            <input
                              className="w-full px-3 py-2 border rounded text-sm"
                              placeholder="标签（逗号分隔）"
                              value={(editSkillForm.tags || []).join(', ')}
                              onChange={e => setEditSkillForm(f => ({ ...f, tags: e.target.value.split(',').map(t => t.trim()) }))}
                            />
                            <div className="flex gap-2">
                              <Button size="sm" onClick={saveEditSkill}>
                                <Save className="w-4 h-4 mr-1" />
                                保存
                              </Button>
                              <Button variant="ghost" size="sm" onClick={cancelEditSkill}>
                                <X className="w-4 h-4 mr-1" />
                                取消
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <h4 className="font-medium text-ink">{skill.name}</h4>
                                <Badge variant="soft" color="blue">v{skill.version}</Badge>
                                <Badge
                                  variant="soft"
                                  className={skill.enabled ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'}
                                >
                                  {skill.enabled ? '已启用' : '已禁用'}
                                </Badge>
                              </div>
                              <p className="text-sm text-slate mb-2">{skill.description}</p>
                              <div className="flex items-center gap-2">
                                {skill.tags.map((tag, i) => (
                                  <span key={i} className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            </div>
                            <div className="flex items-center gap-2 ml-4">
                              {selectedAgent && (
                                <Button variant="ghost" size="sm" onClick={() => setShowRelatedDetail({
                                  open: true,
                                  type: 'skill',
                                  itemId: skill.id,
                                  name: skill.name,
                                })}>
                                  <Info className="w-4 h-4 mr-1" />
                                  详情
                                </Button>
                              )}
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => toggleSkill(skill.id)}
                                disabled={pendingAction === `skill:${selectedAgent}:${skill.id}`}
                              >
                                {skill.enabled ? (
                                  <><ToggleRight className="w-5 h-5 text-green-500" /></>
                                ) : (
                                  <><ToggleLeft className="w-5 h-5 text-slate-400" /></>
                                )}
                              </Button>
                              <Button variant="ghost" size="sm" onClick={() => startEditSkill(skill)}>
                                <Edit className="w-4 h-4" />
                              </Button>
                              <Button variant="ghost" size="sm" onClick={() => deleteSkill(skill.id)}>
                                <Trash2 className="w-4 h-4 text-red-500" />
                              </Button>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </Card>
              </TabsContent>

              {/* Timers Tab */}
              <TabsContent value="timers">
                <Card className="p-6">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <h3 className="text-lg font-semibold text-ink">定时器管理</h3>
                      <p className="text-sm text-slate mt-1">配置Agent的定时任务与Cron表达式</p>
                    </div>
                    <Button size="sm" onClick={() => setShowAddTimer(true)}>
                      <Plus className="w-4 h-4 mr-1" />
                      添加定时器
                    </Button>
                  </div>
                  {showAddTimer && (
                    <div className="mb-4 p-4 bg-orange-50 rounded-lg border border-orange-200">
                      <h4 className="font-medium text-orange-800 mb-3">添加定时器</h4>
                      <div className="space-y-3">
                        <input className="w-full px-3 py-2 border rounded text-sm" placeholder="定时器名称" value={newTimerForm.name} onChange={e => setNewTimerForm(f => ({ ...f, name: e.target.value }))} />
                        <div className="grid grid-cols-5 gap-2">
                          <CronSelect label="分钟" value={newCron.minute} onChange={v => setNewCron(c => ({ ...c, minute: v }))} options={minuteOptions} />
                          <CronSelect label="小时" value={newCron.hour} onChange={v => setNewCron(c => ({ ...c, hour: v }))} options={hourOptions} />
                          <CronSelect label="日" value={newCron.day} onChange={v => setNewCron(c => ({ ...c, day: v }))} options={dayOptions} />
                          <CronSelect label="月" value={newCron.month} onChange={v => setNewCron(c => ({ ...c, month: v }))} options={monthOptions} />
                          <CronSelect label="星期" value={newCron.weekday} onChange={v => setNewCron(c => ({ ...c, weekday: v }))} options={weekdayOptions} />
                        </div>
                        <p className="text-xs text-slate-500 font-mono">Cron 表达式: {buildCron(newCron.minute, newCron.hour, newCron.day, newCron.month, newCron.weekday)}</p>
                        <input className="w-full px-3 py-2 border rounded text-sm" placeholder="执行动作" value={newTimerForm.action} onChange={e => setNewTimerForm(f => ({ ...f, action: e.target.value }))} />
                        <div className="flex gap-2">
                          <Button size="sm" onClick={addTimer}>确认添加</Button>
                          <Button variant="ghost" size="sm" onClick={() => setShowAddTimer(false)}>取消</Button>
                        </div>
                      </div>
                    </div>
                  )}
                  <div className="space-y-4">
                    {currentTimers.length > 0 ? (
                      currentTimers.map((timer) => (
                        <div
                          key={timer.id}
                          className="p-4 bg-white rounded-lg border border-hairline"
                        >
                          {editingTimerId === timer.id ? (
                            <div className="space-y-3">
                              <h4 className="font-medium text-ink">编辑定时器</h4>
                              <input
                                className="w-full px-3 py-2 border rounded text-sm"
                                placeholder="定时器名称"
                                value={editTimerForm.name || ''}
                                onChange={e => setEditTimerForm(f => ({ ...f, name: e.target.value }))}
                              />
                              <div className="grid grid-cols-5 gap-2">
                                <CronSelect label="分钟" value={editCron.minute} onChange={v => setEditCron(c => ({ ...c, minute: v }))} options={minuteOptions} />
                                <CronSelect label="小时" value={editCron.hour} onChange={v => setEditCron(c => ({ ...c, hour: v }))} options={hourOptions} />
                                <CronSelect label="日" value={editCron.day} onChange={v => setEditCron(c => ({ ...c, day: v }))} options={dayOptions} />
                                <CronSelect label="月" value={editCron.month} onChange={v => setEditCron(c => ({ ...c, month: v }))} options={monthOptions} />
                                <CronSelect label="星期" value={editCron.weekday} onChange={v => setEditCron(c => ({ ...c, weekday: v }))} options={weekdayOptions} />
                              </div>
                              <p className="text-xs text-slate-500 font-mono">Cron 表达式: {buildCron(editCron.minute, editCron.hour, editCron.day, editCron.month, editCron.weekday)}</p>
                              <input
                                className="w-full px-3 py-2 border rounded text-sm"
                                placeholder="执行动作"
                                value={editTimerForm.action || ''}
                                onChange={e => setEditTimerForm(f => ({ ...f, action: e.target.value }))}
                              />
                              <div className="flex gap-2">
                                <Button size="sm" onClick={saveEditTimer}>
                                  <Save className="w-4 h-4 mr-1" />
                                  保存
                                </Button>
                                <Button variant="ghost" size="sm" onClick={cancelEditTimer}>
                                  <X className="w-4 h-4 mr-1" />
                                  取消
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <div className="flex items-center gap-2 mb-1">
                                  <h4 className="font-medium text-ink">{timer.name}</h4>
                                  <Badge
                                    variant="soft"
                                    className={timer.enabled ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'}
                                  >
                                    {timer.enabled ? '运行中' : '已暂停'}
                                  </Badge>
                                </div>
                                <div className="flex items-center gap-4 mt-2 text-sm text-slate">
                                  <span className="font-mono bg-slate-100 px-2 py-0.5 rounded">
                                    {timer.cron_expression}
                                  </span>
                                  <span>动作: {timer.action}</span>
                                </div>
                                <div className="flex items-center gap-4 mt-2 text-xs text-slate">
                                  <span>上次执行: {timer.last_run ? new Date(timer.last_run).toLocaleString('zh-CN') : '从未执行'}</span>
                                  <span>下次执行: {timer.next_run ? new Date(timer.next_run).toLocaleString('zh-CN') : '-'}</span>
                                </div>
                              </div>
                              <div className="flex items-center gap-2 ml-4">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => toggleTimer(timer.id)}
                                  disabled={pendingAction === `timer:${selectedAgent}:${timer.id}`}
                                >
                                  {timer.enabled ? (
                                    <><ToggleRight className="w-5 h-5 text-green-500" /></>
                                  ) : (
                                    <><ToggleLeft className="w-5 h-5 text-slate-400" /></>
                                  )}
                                </Button>
                                <Button variant="ghost" size="sm" onClick={() => startEditTimer(timer)}>
                                  <Edit className="w-4 h-4" />
                                </Button>
                                <Button variant="ghost" size="sm" onClick={() => deleteTimer(timer.id)}>
                                  <Trash2 className="w-4 h-4 text-red-500" />
                                </Button>
                              </div>
                            </div>
                          )}
                        </div>
                      ))
                    ) : (
                      <div className="text-center py-12">
                        <Clock className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                        <p className="text-slate-500">暂无定时器配置</p>
                      </div>
                    )}
                  </div>
                </Card>
              </TabsContent>

              {/* Memory Tab */}
              <TabsContent value="memory">
                <Card className="p-6">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <h3 className="text-lg font-semibold text-ink">记忆管理</h3>
                      <p className="text-sm text-slate mt-1">查看和管理Agent的记忆存储</p>
                    </div>
                  </div>
                  <div className="space-y-4">
                    {currentMemories.length > 0 ? (
                      currentMemories.map((memory) => (
                        <div
                          key={memory.id}
                          className="p-4 bg-white rounded-lg border border-hairline flex items-start justify-between"
                        >
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              <h4 className="font-medium text-ink">{memory.name}</h4>
                              <Badge variant="soft" className={memoryTypeColors[memory.type]}>
                                {memoryTypeLabels[memory.type]}
                              </Badge>
                            </div>
                            <div className="flex items-center gap-6 text-sm text-slate">
                              <div className="flex items-center gap-2">
                                <Database className="w-4 h-4" />
                                <span>大小: {formatBytes(memory.size)}</span>
                              </div>
                              <div className="flex items-center gap-2">
                                <span>条目数: {memory.item_count}</span>
                              </div>
                              <div className="flex items-center gap-2">
                                <Clock className="w-4 h-4" />
                                <span>更新: {new Date(memory.last_updated).toLocaleString('zh-CN')}</span>
                              </div>
                            </div>
                            {/* Progress Bar */}
                            <div className="mt-3">
                              <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-brand-green rounded-full transition-all"
                                  style={{
                                    width: `${Math.min((memory.size / 10485760) * 100, 100)}%`,
                                  }}
                                />
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 ml-4">
                            <Button variant="ghost" size="sm" onClick={() => setViewMemory(memory)}>
                              <FolderOpen className="w-4 h-4 mr-1" />
                              查看
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => clearMemory(memory.id)}
                              disabled={pendingAction === `memory:${selectedAgent}:${memory.id}`}
                            >
                              <Trash2 className="w-4 h-4 text-red-500 mr-1" />
                              清空
                            </Button>
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="text-center py-12">
                        <Database className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                        <p className="text-slate-500">暂无记忆存储</p>
                      </div>
                    )}
                  </div>
                </Card>

                  {/* Memory Detail Dialog */}
                {viewMemory && (
                  <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
                    <Card className="w-full max-w-2xl p-6 relative animate-in fade-in zoom-in-95 max-h-[85vh] flex flex-col">
                      <button
                        onClick={() => setViewMemory(null)}
                        className="absolute top-4 right-4 p-1 hover:bg-slate-100 rounded transition-colors"
                      >
                        <X className="w-5 h-5 text-slate" />
                      </button>
                      <div className="flex items-center gap-3 mb-6">
                        <div className="w-10 h-10 rounded-xl bg-brand-green/10 flex items-center justify-center">
                          <Database className="w-5 h-5 text-brand-green" />
                        </div>
                        <div>
                          <h3 className="text-lg font-semibold text-ink">{viewMemory.name}</h3>
                          <Badge variant="soft" className={memoryTypeColors[viewMemory.type]}>
                            {memoryTypeLabels[viewMemory.type]}
                          </Badge>
                        </div>
                      </div>
                      <div className="space-y-4 overflow-auto flex-1">
                        <div className="grid grid-cols-2 gap-4">
                          <div className="p-4 bg-slate-50 rounded-lg">
                            <p className="text-xs text-slate mb-1">存储大小</p>
                            <p className="text-lg font-semibold text-ink">{formatBytes(viewMemory.size)}</p>
                          </div>
                          <div className="p-4 bg-slate-50 rounded-lg">
                            <p className="text-xs text-slate mb-1">条目数</p>
                            <p className="text-lg font-semibold text-ink">{viewMemory.item_count}</p>
                          </div>
                        </div>
                        <div className="p-4 bg-slate-50 rounded-lg">
                          <p className="text-xs text-slate mb-1">最后更新</p>
                          <p className="text-sm text-ink">{new Date(viewMemory.last_updated).toLocaleString('zh-CN')}</p>
                        </div>
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-xs text-slate">存储使用率</span>
                            <span className="text-xs text-slate">{Math.min(Math.round((viewMemory.size / 10485760) * 100), 100)}%</span>
                          </div>
                          <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-brand-green rounded-full transition-all"
                              style={{ width: `${Math.min((viewMemory.size / 10485760) * 100, 100)}%` }}
                            />
                          </div>
                        </div>
                        {/* Memory Content */}
                        {viewMemory.content && (
                          <div>
                            <h4 className="text-sm font-medium text-ink mb-2">内容预览</h4>
                            <CodeBlock language="json">{viewMemory.content}</CodeBlock>
                          </div>
                        )}
                        {/* Memory Entries */}
                        {viewMemory.entries && viewMemory.entries.length > 0 && (
                          <div>
                            <h4 className="text-sm font-medium text-ink mb-2">
                              记忆条目 ({viewMemory.entries.length})
                            </h4>
                            <div className="space-y-2 max-h-48 overflow-auto">
                              {viewMemory.entries.map((entry) => (
                                <div
                                  key={entry.id}
                                  className="p-3 bg-slate-50 rounded-lg border border-hairline"
                                >
                                  <div className="flex items-start justify-between">
                                    <div className="flex-1 min-w-0">
                                      <div className="flex items-center gap-2 mb-1">
                                        <Badge variant="soft" className="bg-blue-100 text-blue-700 text-xs">
                                          {entry.type}
                                        </Badge>
                                        <span className="text-sm font-medium text-ink truncate">{entry.key}</span>
                                      </div>
                                      <p className="text-xs text-slate line-clamp-3">{entry.value}</p>
                                      {entry.score !== undefined && (
                                        <span className="text-xs text-slate mt-1 inline-block">
                                          相关度: {Math.round(entry.score * 100)}%
                                        </span>
                                      )}
                                    </div>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => deleteMemoryEntry(viewMemory.id, entry.id)}
                                      disabled={pendingAction === `memory_entry:${selectedAgent}:${viewMemory.id}:${entry.id}`}
                                    >
                                      <Trash2 className="w-4 h-4 text-red-500" />
                                    </Button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                      <div className="mt-6 pt-4 border-t border-hairline flex justify-end">
                        <Button size="sm" onClick={() => setViewMemory(null)}>
                          关闭
                        </Button>
                      </div>
                    </Card>
                  </div>
                )}
              </TabsContent>

              {/* Config Tab */}
              <TabsContent value="config">
                <Card className="p-6">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <h3 className="text-lg font-semibold text-ink">Agent配置</h3>
                      <p className="text-sm text-slate mt-1">编辑此Agent的核心配置参数</p>
                    </div>
                    {editingConfig ? (
                      <div className="flex gap-2">
                        <Button variant="ghost" size="sm" onClick={() => setEditingConfig(false)}>
                          <X className="w-4 h-4 mr-1" />
                          取消
                        </Button>
                        <Button size="sm" onClick={saveConfig} disabled={pendingAction === `config:${selectedAgent}`}>
                          <Save className="w-4 h-4 mr-1" />
                          保存
                        </Button>
                      </div>
                    ) : (
                      <Button size="sm" onClick={startEditConfig}>
                        <Edit className="w-4 h-4 mr-1" />
                        编辑配置
                      </Button>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-6">
                    <div>
                      <label className="block text-sm font-medium text-ink mb-2">Agent名称</label>
                      <Input
                        value={editingConfig ? editForm.name : currentAgent.name}
                        onChange={(e) => setEditForm(prev => ({ ...prev, name: e.target.value }))}
                        disabled={!editingConfig}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-ink mb-2">角色类型</label>
                      <Input
                        value={roleLabels[editingConfig ? editForm.role! : currentAgent.role]}
                        disabled
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-ink mb-2">模型</label>
                      <Input
                        value={editingConfig ? editForm.model : currentAgent.model}
                        onChange={(e) => setEditForm(prev => ({ ...prev, model: e.target.value }))}
                        disabled={!editingConfig}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-ink mb-2">Temperature</label>
                        <Input
                          type="number"
                          step="0.1"
                          min="0"
                          max="2"
                          value={editingConfig ? editForm.temperature : currentAgent.temperature}
                          onChange={(e) => setEditForm(prev => ({ ...prev, temperature: parseFloat(e.target.value) }))}
                          disabled={!editingConfig}
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-ink mb-2">Max Tokens</label>
                        <Input
                          type="number"
                          value={editingConfig ? editForm.max_tokens : currentAgent.max_tokens}
                          onChange={(e) => setEditForm(prev => ({ ...prev, max_tokens: parseInt(e.target.value) }))}
                          disabled={!editingConfig}
                        />
                      </div>
                    </div>
                    <div className="col-span-2">
                      <label className="block text-sm font-medium text-ink mb-2">工作目录</label>
                      <div className="flex gap-2">
                        <div className="flex-1">
                          <Input
                            value={editingConfig ? editForm.working_directory : currentAgent.working_directory}
                            onChange={(e) => setEditForm(prev => ({ ...prev, working_directory: e.target.value }))}
                            disabled={!editingConfig}
                            icon={<FolderOpen className="w-4 h-4" />}
                          />
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={browseWorkingDir}
                          disabled={isLoadingFiles}
                        >
                          <Search className="w-4 h-4 mr-1" />
                          浏览
                        </Button>
                      </div>
                      {browseEntries !== null && (
                        <div className="mt-2 p-3 bg-slate-50 rounded-lg border border-hairline max-h-60 overflow-auto">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-xs font-mono text-slate truncate">{browseCurrentPath || '/'}</span>
                            <div className="flex gap-1">
                              {browsePathStack.length > 0 && (
                                <Button variant="ghost" size="sm" onClick={navigateUp} disabled={isLoadingFiles}>
                                  ← 返回
                                </Button>
                              )}
                              <Button variant="ghost" size="sm" onClick={browseWorkingDir} disabled={isLoadingFiles}>
                                <RefreshCw className={`w-3 h-3 ${isLoadingFiles ? 'animate-spin' : ''}`} />
                              </Button>
                            </div>
                          </div>
                          {isLoadingFiles ? (
                            <p className="text-sm text-slate text-center py-4">加载中...</p>
                          ) : browseEntries.length === 0 ? (
                            <p className="text-sm text-slate text-center py-4">空目录</p>
                          ) : (
                            <div className="space-y-1">
                              {browseEntries.map((entry) => (
                                <div
                                  key={entry.path}
                                  className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-slate-100 cursor-pointer text-xs"
                                  onClick={() => {
                                    if (entry.type === 'directory') {
                                      navigateToDir(entry.path);
                                    } else {
                                      openFileContent(entry.path);
                                    }
                                  }}
                                >
                                  {entry.type === 'directory' ? (
                                    <FolderOpen className="w-3.5 h-3.5 text-blue-500 flex-shrink-0" />
                                  ) : (
                                    <FileText className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                                  )}
                                  <span className="font-mono text-slate-700 truncate">{entry.name}</span>
                                  {entry.type === 'file' && (
                                    <span className="text-slate-400 flex-shrink-0 ml-auto">{formatBytes(entry.size)}</span>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="col-span-2">
                      <label className="block text-sm font-medium text-ink mb-2">描述</label>
                      <Input
                        value={editingConfig ? editForm.description : currentAgent.description}
                        onChange={(e) => setEditForm(prev => ({ ...prev, description: e.target.value }))}
                        disabled={!editingConfig}
                      />
                    </div>
                    <div className="col-span-2">
                      <div className="flex items-center justify-between mb-2">
                        <label className="block text-sm font-medium text-ink">System Prompt</label>
                        <Button variant="ghost" size="sm" onClick={() => setViewSystemPrompt(true)}>
                          <Eye className="w-4 h-4 mr-1" />
                          全屏查看
                        </Button>
                      </div>
                      <Textarea
                        value={editingConfig ? editForm.system_prompt : currentAgent.system_prompt}
                        onChange={(e) => setEditForm(prev => ({ ...prev, system_prompt: e.target.value }))}
                        disabled={!editingConfig}
                        rows={6}
                      />
                    </div>
                  </div>

                  {/* Meta Info */}
                  <div className="mt-8 pt-6 border-t border-hairline">
                    <h4 className="text-sm font-medium text-ink mb-4">元信息</h4>
                    <div className="grid grid-cols-3 gap-4 text-sm">
                      <div>
                        <span className="text-slate">创建时间</span>
                        <p className="text-ink mt-1">{new Date(currentAgent.created_at).toLocaleString('zh-CN')}</p>
                      </div>
                      <div>
                        <span className="text-slate">更新时间</span>
                        <p className="text-ink mt-1">{new Date(currentAgent.updated_at).toLocaleString('zh-CN')}</p>
                      </div>
                      <div>
                        <span className="text-slate">父级Agent</span>
                        <p className="text-ink mt-1">
                          {currentAgent.parent_id
                            ? agents.find(a => a.id === currentAgent.parent_id)?.name
                            : '无 (根节点)'}
                        </p>
                      </div>
                    </div>
                  </div>
                </Card>
              </TabsContent>

              {/* Model Config Tab */}
              <TabsContent value="model-config">
                <div className="space-y-4">
                  <p className="text-body-sm text-slate">
                    为该 Agent 单独配置文字 LLM 和生图供应商。未配置时回退到全局默认值。
                    API key 会以加密形式存储。
                  </p>
                  {selectedAgent && (
                    <>
                      <AgentModelConfigPanel
                        agentId={selectedAgent}
                        kind="llm"
                        initial={modelConfigs[selectedAgent]?.llm ?? null}
                        onSaved={(resolved) => {
                          setModelConfigs((prev) => ({
                            ...prev,
                            [selectedAgent]: {
                              ...(prev[selectedAgent] || { image_gen: null }),
                              llm: resolved,
                            },
                          }));
                        }}
                      />
                      <AgentModelConfigPanel
                        agentId={selectedAgent}
                        kind="image_gen"
                        initial={modelConfigs[selectedAgent]?.image_gen ?? null}
                        onSaved={(resolved) => {
                          setModelConfigs((prev) => ({
                            ...prev,
                            [selectedAgent]: {
                              ...(prev[selectedAgent] || { llm: null }),
                              image_gen: resolved,
                            },
                          }));
                        }}
                      />
                    </>
                  )}
                </div>
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </div>
    </div>

      {/* Tool Source Code Modal */}
      {viewToolSource && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <Card className="w-full max-w-3xl p-6 relative animate-in fade-in zoom-in-95 max-h-[85vh] flex flex-col">
            <button
              onClick={() => setViewToolSource(null)}
              className="absolute top-4 right-4 p-1 hover:bg-slate-100 rounded transition-colors"
            >
              <X className="w-5 h-5 text-slate" />
            </button>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-brand-green/10 flex items-center justify-center">
                <Code className="w-5 h-5 text-brand-green" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-ink">{viewToolSource.name}</h3>
                <p className="text-sm text-slate">工具源代码</p>
              </div>
            </div>
            <div className="overflow-auto flex-1">
              <CodeBlock language={viewToolSource.source_code?.startsWith('{') ? 'json' : 'typescript'}>
                {viewToolSource.source_code}
              </CodeBlock>
            </div>
            <div className="mt-6 pt-4 border-t border-hairline flex justify-end">
              <Button size="sm" onClick={() => setViewToolSource(null)}>
                关闭
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* System Prompt Fullscreen Modal */}
      {viewSystemPrompt && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <Card className="w-full max-w-4xl p-6 relative animate-in fade-in zoom-in-95 max-h-[85vh] flex flex-col">
            <button
              onClick={() => setViewSystemPrompt(false)}
              className="absolute top-4 right-4 p-1 hover:bg-slate-100 rounded transition-colors"
            >
              <X className="w-5 h-5 text-slate" />
            </button>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-brand-green/10 flex items-center justify-center">
                <FileText className="w-5 h-5 text-brand-green" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-ink">System Prompt</h3>
                <p className="text-sm text-slate">{currentAgent?.name || ''}</p>
              </div>
            </div>
            <div className="overflow-auto flex-1">
              <CodeBlock language="markdown">
                {currentAgent?.system_prompt || ''}
              </CodeBlock>
            </div>
            <div className="mt-6 pt-4 border-t border-hairline flex justify-end">
              <Button size="sm" onClick={() => setViewSystemPrompt(false)}>
                关闭
              </Button>
            </div>
          </Card>
        </div>
      )}

       {/* File Content Viewer Modal */}
       {fileContent && (
         <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
           <Card className="w-full max-w-4xl p-6 relative animate-in fade-in zoom-in-95 max-h-[85vh] flex flex-col">
             <button
               onClick={() => setFileContent(null)}
               className="absolute top-4 right-4 p-1 hover:bg-slate-100 rounded transition-colors"
             >
               <X className="w-5 h-5 text-slate" />
             </button>
             <div className="flex items-center gap-3 mb-6">
               <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
                 <FileText className="w-5 h-5 text-blue-500" />
               </div>
               <div>
                 <h3 className="text-lg font-semibold text-ink truncate max-w-lg">{fileContent.path.split('/').pop()}</h3>
                 <p className="text-sm text-slate truncate max-w-lg">{fileContent.path}</p>
               </div>
             </div>
             <div className="overflow-auto flex-1">
               {isLoadingFileContent ? (
                 <p className="text-sm text-slate text-center py-8">加载中...</p>
               ) : fileContent.content ? (
                 <CodeBlock language={fileContent.path.endsWith('.json') ? 'json' : fileContent.path.endsWith('.py') ? 'python' : fileContent.path.endsWith('.ts') || fileContent.path.endsWith('.tsx') ? 'typescript' : fileContent.path.endsWith('.js') ? 'javascript' : fileContent.path.endsWith('.md') ? 'markdown' : fileContent.path.endsWith('.yaml') || fileContent.path.endsWith('.yml') ? 'yaml' : fileContent.path.endsWith('.html') ? 'html' : fileContent.path.endsWith('.css') ? 'css' : fileContent.path.endsWith('.sh') ? 'bash' : 'text'}>
                   {fileContent.content.length > 50000
                     ? fileContent.content.slice(0, 50000) + '\n\n... (文件过大，已截断)'
                     : fileContent.content}
                 </CodeBlock>
               ) : (
                 <p className="text-sm text-slate text-center py-8">无法读取文件内容 (二进制文件)</p>
               )}
             </div>
             <div className="mt-6 pt-4 border-t border-hairline flex justify-end gap-2">
               <Button size="sm" variant="ghost" onClick={() => setFileContent(null)}>
                 关闭
               </Button>
               <Button size="sm" onClick={() => { navigator.clipboard?.writeText(fileContent.content); setFileContent(null); }}>
                 复制内容
               </Button>
             </div>
           </Card>
         </div>
       )}

       {/* Hermes Tool Chat Modal */}
       {showHermesChat && selectedAgent && (
         <HermesToolChatModal
           agentId={selectedAgent}
           onClose={() => setShowHermesChat(false)}
           onToolCreated={(_data) => { void loadAgentDetail(selectedAgent); }}
         />
       )}

       {/* Hermes Skill Chat Modal */}
       {showHermesSkillChat && selectedAgent && (
         <HermesSkillChatModal
           agentId={selectedAgent}
           onClose={() => setShowHermesSkillChat(false)}
           onSkillCreated={(_data) => { void loadAgentDetail(selectedAgent); }}
         />
       )}

      {/* Related Detail Modal */}
      {showRelatedDetail?.open && selectedAgent && (
        <RelatedDetailModal
          agentId={selectedAgent}
          type={showRelatedDetail.type}
          name={showRelatedDetail.name}
          itemId={showRelatedDetail.itemId}
          onClose={() => setShowRelatedDetail(null)}
        />
      )}

      {/* Skill Upload Modal */}
      {showSkillUpload && selectedAgent && (
        <SkillUploadModal
          agentId={selectedAgent}
          onClose={() => setShowSkillUpload(false)}
          onSkillCreated={(_data) => { void loadAgentDetail(selectedAgent); }}
        />
      )}

      <ConfirmDialog
        open={confirmDialog.open}
        title={confirmDialog.title}
        message={confirmDialog.message}
        confirmLabel="确认删除"
        variant="danger"
        onConfirm={confirmDialog.onConfirm}
        onCancel={() => setConfirmDialog(prev => ({ ...prev, open: false }))}
      />
    </>
  );
}
