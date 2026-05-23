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
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs';
import { Textarea } from '@/components/ui/Textarea';
import { agentApi } from '@/lib/api';
import type { AgentConfig, AgentTool, AgentSkill, AgentTimer, AgentMemory } from '@/types';

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
  const [viewMemory, setViewMemory] = useState<AgentMemory | null>(null);

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

  // Tool/Skill/Timer CRUD handlers
  const startEditTool = (tool: AgentTool) => {
    setEditingToolId(tool.id);
    setEditToolForm({ ...tool });
  };
  const cancelEditTool = () => { setEditingToolId(null); setEditToolForm({}); };
  const saveEditTool = () => {
    if (!selectedAgent) return;
    const updated = currentTools.map(t => t.id === editingToolId ? { ...t, ...editToolForm } as AgentTool : t);
    setTools(prev => ({ ...prev, [selectedAgent]: updated }));
    setEditingToolId(null);
    setEditToolForm({});
  };
  const deleteTool = (toolId: string) => {
    if (!selectedAgent || !window.confirm('确定要删除此工具吗？')) return;
    setTools(prev => ({ ...prev, [selectedAgent]: (prev[selectedAgent] || []).filter(t => t.id !== toolId) }));
  };

  const startEditSkill = (skill: AgentSkill) => {
    setEditingSkillId(skill.id);
    setEditSkillForm({ ...skill });
  };
  const cancelEditSkill = () => { setEditingSkillId(null); setEditSkillForm({}); };
  const saveEditSkill = () => {
    if (!selectedAgent) return;
    const updated = currentSkills.map(s => s.id === editingSkillId ? { ...s, ...editSkillForm } as AgentSkill : s);
    setSkills(prev => ({ ...prev, [selectedAgent]: updated }));
    setEditingSkillId(null);
    setEditSkillForm({});
  };
  const deleteSkill = (skillId: string) => {
    if (!selectedAgent || !window.confirm('确定要删除此技能吗？')) return;
    setSkills(prev => ({ ...prev, [selectedAgent]: (prev[selectedAgent] || []).filter(s => s.id !== skillId) }));
  };

  const startEditTimer = (timer: AgentTimer) => {
    setEditingTimerId(timer.id);
    setEditTimerForm({ ...timer });
  };
  const cancelEditTimer = () => { setEditingTimerId(null); setEditTimerForm({}); };
  const saveEditTimer = () => {
    if (!selectedAgent) return;
    const updated = currentTimers.map(t => t.id === editingTimerId ? { ...t, ...editTimerForm } as AgentTimer : t);
    setTimers(prev => ({ ...prev, [selectedAgent]: updated }));
    setEditingTimerId(null);
    setEditTimerForm({});
  };
  const deleteTimer = (timerId: string) => {
    if (!selectedAgent || !window.confirm('确定要删除此定时器吗？')) return;
    setTimers(prev => ({ ...prev, [selectedAgent]: (prev[selectedAgent] || []).filter(t => t.id !== timerId) }));
  };

  const addTool = () => {
    if (!selectedAgent) return;
    const newTool: AgentTool = { id: `tool_${Date.now()}`, ...newToolForm, enabled: true };
    setTools(prev => ({ ...prev, [selectedAgent]: [...(prev[selectedAgent] || []), newTool] }));
    setShowAddTool(false);
    setNewToolForm({ name: '', description: '', category: 'search' });
  };
  const addSkill = () => {
    if (!selectedAgent) return;
    const newSkill: AgentSkill = {
      id: `skill_${Date.now()}`, name: newSkillForm.name, description: newSkillForm.description,
      tags: newSkillForm.tags ? newSkillForm.tags.split(',').map(t => t.trim()) : [], version: '1.0.0', enabled: true,
    };
    setSkills(prev => ({ ...prev, [selectedAgent]: [...(prev[selectedAgent] || []), newSkill] }));
    setShowAddSkill(false);
    setNewSkillForm({ name: '', description: '', tags: '' });
  };
  const addTimer = () => {
    if (!selectedAgent) return;
    const newTimer: AgentTimer = { id: `timer_${Date.now()}`, ...newTimerForm, enabled: true };
    setTimers(prev => ({ ...prev, [selectedAgent]: [...(prev[selectedAgent] || []), newTimer] }));
    setShowAddTimer(false);
    setNewTimerForm({ name: '', cron_expression: '0 * * * *', action: '' });
  };

  if (isLoadingAgents) {
    return (
      <div className="min-h-screen bg-surface p-6">
        <Card className="p-12 text-center">
          <RefreshCw className="w-10 h-10 text-slate mx-auto mb-4 animate-spin" />
          <h3 className="text-lg font-medium text-ink mb-2">正在加载 Agent 配置</h3>
          <p className="text-sm text-slate">正在读取 Hermes Profile 注册表...</p>
        </Card>
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
              </TabsList>

              {/* Tools Tab */}
              <TabsContent value="tools">
                <Card className="p-6">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <h3 className="text-lg font-semibold text-ink">工具列表</h3>
                      <p className="text-sm text-slate mt-1">管理此Agent可用的工具集</p>
                    </div>
                    <Button size="sm" onClick={() => setShowAddTool(true)}>
                      <Plus className="w-4 h-4 mr-1" />
                      添加工具
                    </Button>
                  </div>
                  {showAddTool && (
                    <div className="mb-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
                      <h4 className="font-medium text-blue-800 mb-3">添加新工具</h4>
                      <div className="space-y-3">
                        <input className="w-full px-3 py-2 border rounded text-sm" placeholder="工具名称" value={newToolForm.name} onChange={e => setNewToolForm(f => ({ ...f, name: e.target.value }))} />
                        <input className="w-full px-3 py-2 border rounded text-sm" placeholder="工具描述" value={newToolForm.description} onChange={e => setNewToolForm(f => ({ ...f, description: e.target.value }))} />
                        <select className="w-full px-3 py-2 border rounded text-sm" value={newToolForm.category} onChange={e => setNewToolForm(f => ({ ...f, category: e.target.value as AgentTool['category'] }))}>
                          <option value="search">Search</option>
                          <option value="analysis">Analysis</option>
                          <option value="generation">Generation</option>
                          <option value="utility">Utility</option>
                        </select>
                        <div className="flex gap-2">
                          <Button size="sm" onClick={addTool}>确认添加</Button>
                          <Button variant="ghost" size="sm" onClick={() => setShowAddTool(false)}>取消</Button>
                        </div>
                      </div>
                    </div>
                  )}
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
                    <Button size="sm" onClick={() => setShowAddSkill(true)}>
                      <Plus className="w-4 h-4 mr-1" />
                      安装技能
                    </Button>
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
                  {showAddSkill && (
                    <div className="mt-4 p-4 bg-purple-50 rounded-lg border border-purple-200">
                      <h4 className="font-medium text-purple-800 mb-3">安装新技能</h4>
                      <div className="space-y-3">
                        <input className="w-full px-3 py-2 border rounded text-sm" placeholder="技能名称" value={newSkillForm.name} onChange={e => setNewSkillForm(f => ({ ...f, name: e.target.value }))} />
                        <input className="w-full px-3 py-2 border rounded text-sm" placeholder="技能描述" value={newSkillForm.description} onChange={e => setNewSkillForm(f => ({ ...f, description: e.target.value }))} />
                        <input className="w-full px-3 py-2 border rounded text-sm" placeholder="标签（逗号分隔）" value={newSkillForm.tags} onChange={e => setNewSkillForm(f => ({ ...f, tags: e.target.value }))} />
                        <div className="flex gap-2">
                          <Button size="sm" onClick={addSkill}>确认安装</Button>
                          <Button variant="ghost" size="sm" onClick={() => setShowAddSkill(false)}>取消</Button>
                        </div>
                      </div>
                    </div>
                  )}
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
                        <input className="w-full px-3 py-2 border rounded text-sm" placeholder="Cron 表达式" value={newTimerForm.cron_expression} onChange={e => setNewTimerForm(f => ({ ...f, cron_expression: e.target.value }))} />
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
                              <input
                                className="w-full px-3 py-2 border rounded text-sm font-mono"
                                placeholder="Cron 表达式"
                                value={editTimerForm.cron_expression || ''}
                                onChange={e => setEditTimerForm(f => ({ ...f, cron_expression: e.target.value }))}
                              />
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
                    <Card className="w-full max-w-lg p-6 relative animate-in fade-in zoom-in-95">
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
                      <div className="space-y-4">
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
                        {/* Progress Bar */}
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
                      <Input
                        value={editingConfig ? editForm.working_directory : currentAgent.working_directory}
                        onChange={(e) => setEditForm(prev => ({ ...prev, working_directory: e.target.value }))}
                        disabled={!editingConfig}
                        icon={<FolderOpen className="w-4 h-4" />}
                      />
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
                      <label className="block text-sm font-medium text-ink mb-2">System Prompt</label>
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
            </Tabs>
          </div>
        </div>
      </div>
    </div>
  );
}
