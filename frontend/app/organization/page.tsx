'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  GitBranch,
  ChevronRight,
  ChevronDown,
  Bot,
  Users,
  UserPlus,
  Trash2,
  Edit,
  GripVertical,
  Plus,
  X,
  Save,
  Settings,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { organizationApi } from '@/lib/api';
import type { OrgNode } from '@/types';

const emptyOrgTree: OrgNode = {
  id: 'root',
  name: '专利智能体系统',
  type: 'team',
  description: '正在加载组织架构',
  expanded: true,
  children: [],
};


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

const typeIcons: Record<string, React.ReactNode> = {
  team: <Users className="w-5 h-5" />,
  group: <GitBranch className="w-5 h-5" />,
  agent: <Bot className="w-5 h-5" />,
};

const typeColors: Record<string, string> = {
  team: 'bg-brand-green text-white',
  group: 'bg-blue-500 text-white',
  agent: 'bg-purple-500 text-white',
};

const typeLabels: Record<string, string> = {
  team: '团队',
  group: '小组',
  agent: 'Agent',
};

interface TreeNodeProps {
  node: OrgNode;
  level: number;
  selectedId: string | null;
  onSelect: (node: OrgNode) => void;
  onToggle: (nodeId: string) => void;
  onEdit: (node: OrgNode) => void;
  onDelete: (node: OrgNode) => void;
  onDragStart: (node: OrgNode) => void;
  onDragOver: (e: React.DragEvent, targetNode: OrgNode) => void;
  onDrop: (targetNode: OrgNode) => void;
  dragNodeId: string | null;
  dropTargetId: string | null;
}

function TreeNode({
  node,
  level,
  selectedId,
  onSelect,
  onToggle,
  onEdit,
  onDelete,
  onDragStart,
  onDragOver,
  onDrop,
  dragNodeId,
  dropTargetId,
}: TreeNodeProps) {
  const hasChildren = node.children && node.children.length > 0;
  const isExpanded = node.expanded !== false;
  const isSelected = selectedId === node.id;
  const isDragging = dragNodeId === node.id;
  const isDropTarget = dropTargetId === node.id && node.type !== 'agent';

  return (
    <div className="select-none">
      <div
        className={`group flex items-center gap-2 py-2 px-3 rounded-lg cursor-pointer transition-all ${
          isSelected ? 'bg-brand-green/10 ring-2 ring-brand-green' : 'hover:bg-slate-50'
        } ${isDragging ? 'opacity-50' : ''} ${
          isDropTarget ? 'border-2 border-dashed border-brand-green bg-green-50' : ''
        }`}
        style={{ marginLeft: `${level * 24}px` }}
        draggable
        onDragStart={() => onDragStart(node)}
        onDragOver={(e) => onDragOver(e, node)}
        onDrop={() => onDrop(node)}
        onClick={() => onSelect(node)}
      >
        <GripVertical className="w-4 h-4 text-slate-300 opacity-0 group-hover:opacity-100 cursor-grab flex-shrink-0" />

        {hasChildren ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggle(node.id);
            }}
            className="p-1 hover:bg-slate-100 rounded flex-shrink-0"
          >
            {isExpanded ? (
              <ChevronDown className="w-4 h-4 text-slate-500" />
            ) : (
              <ChevronRight className="w-4 h-4 text-slate-500" />
            )}
          </button>
        ) : (
          <div className="w-6 flex-shrink-0" />
        )}

        <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${typeColors[node.type]}`}>
          {typeIcons[node.type]}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-ink truncate">{node.name}</span>
            <Badge variant="soft" color="slate">
              {typeLabels[node.type]}
            </Badge>
            {node.type === 'agent' && node.agent_config && (
              <Badge
                variant="soft"
                className={
                  node.agent_config.enabled
                    ? 'bg-green-100 text-green-700'
                    : 'bg-slate-100 text-slate-500'
                }
              >
                {node.agent_config.enabled ? '运行中' : '已停用'}
              </Badge>
            )}
          </div>
          <p className="text-xs text-slate truncate">{node.description}</p>
        </div>

        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
          {node.type !== 'team' && (
            <>
              <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onEdit(node); }}>
                <Edit className="w-4 h-4" />
              </Button>
              <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onDelete(node); }}>
                <Trash2 className="w-4 h-4 text-red-500" />
              </Button>
            </>
          )}
        </div>
      </div>

      {hasChildren && isExpanded && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              level={level + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              onToggle={onToggle}
              onEdit={onEdit}
              onDelete={onDelete}
              onDragStart={onDragStart}
              onDragOver={onDragOver}
              onDrop={onDrop}
              dragNodeId={dragNodeId}
              dropTargetId={dropTargetId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function OrganizationPage() {
  const [orgTree, setOrgTree] = useState<OrgNode>(emptyOrgTree);
  const [selectedNode, setSelectedNode] = useState<OrgNode | null>(null);
  const [dragNodeId, setDragNodeId] = useState<string | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  const [editingNode, setEditingNode] = useState(false);
  const [editForm, setEditForm] = useState<Partial<OrgNode>>({});
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [addForm, setAddForm] = useState({ name: '', description: '', type: 'group' as 'group' | 'agent' });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const persistTree = useCallback(async (tree: OrgNode) => {
    setIsSaving(true);
    try {
      await organizationApi.updateTree(tree);
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '保存组织架构失败');
    } finally {
      setIsSaving(false);
    }
  }, []);

  const loadTree = useCallback(async (showLoading = false) => {
    if (showLoading) {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    try {
      const tree = await organizationApi.getTree();
      setOrgTree(tree);
      setSelectedNode(null);
      setEditingNode(false);
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '获取组织架构失败');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadTree(true);
  }, [loadTree]);

  const toggleNode = (nodeId: string, tree: OrgNode = orgTree): OrgNode => {
    if (tree.id === nodeId) {
      return { ...tree, expanded: !tree.expanded };
    }
    return {
      ...tree,
      children: tree.children.map((child) => toggleNode(nodeId, child)),
    };
  };

  const handleToggle = (nodeId: string) => {
    setOrgTree(toggleNode(nodeId));
  };

  const handleSelect = (node: OrgNode) => {
    setSelectedNode(node);
    setEditingNode(false);
  };

  const handleDragStart = (node: OrgNode) => {
    if (node.type === 'team') return;
    setDragNodeId(node.id);
  };

  const handleDragOver = (e: React.DragEvent, targetNode: OrgNode) => {
    e.preventDefault();
    if (targetNode.type !== 'agent' && targetNode.id !== dragNodeId) {
      setDropTargetId(targetNode.id);
    }
  };

  const handleDrop = (targetNode: OrgNode) => {
    if (!dragNodeId || targetNode.type === 'agent' || targetNode.id === dragNodeId) {
      setDragNodeId(null);
      setDropTargetId(null);
      return;
    }

    // Find and remove the dragged node from its current position
    const removeNode = (tree: OrgNode, id: string): { tree: OrgNode; removed: OrgNode | null } => {
      if (tree.id === id) {
        return { tree, removed: tree };
      }
      for (let i = 0; i < tree.children.length; i++) {
        if (tree.children[i].id === id) {
          const removed = tree.children[i];
          const newChildren = [...tree.children];
          newChildren.splice(i, 1);
          return { tree: { ...tree, children: newChildren }, removed };
        }
        const result = removeNode(tree.children[i], id);
        if (result.removed) {
          return {
            tree: { ...tree, children: tree.children.map((c, idx) => idx === i ? result.tree : c) },
            removed: result.removed,
          };
        }
      }
      return { tree, removed: null };
    };

    // Add the node to the target
    const addToTarget = (tree: OrgNode, targetId: string, node: OrgNode): OrgNode => {
      if (tree.id === targetId) {
        return { ...tree, children: [...tree.children, node] };
      }
      return {
        ...tree,
        children: tree.children.map((child) => addToTarget(child, targetId, node)),
      };
    };

    const { tree: treeAfterRemove, removed } = removeNode(orgTree, dragNodeId);
    if (removed) {
      const newTree = addToTarget(treeAfterRemove, targetNode.id, removed);
      setOrgTree(newTree);
      void persistTree(newTree);
    }

    setDragNodeId(null);
    setDropTargetId(null);
  };

  const startEditNode = (node?: OrgNode) => {
    const target = node || selectedNode;
    if (target) {
      setEditForm(target);
      setEditingNode(true);
    }
  };

  const saveEditNode = () => {
    const updateNode = (tree: OrgNode, id: string, updates: Partial<OrgNode>): OrgNode => {
      if (tree.id === id) {
        return { ...tree, ...updates };
      }
      return {
        ...tree,
        children: tree.children.map((child) => updateNode(child, id, updates)),
      };
    };
    if (!selectedNode) return;
    const newTree = updateNode(orgTree, selectedNode.id, editForm);
    const newSelectedNode = { ...selectedNode, ...editForm };
    setOrgTree(newTree);
    setSelectedNode(newSelectedNode);
    setEditingNode(false);
    void persistTree(newTree);
  };

  const deleteNode = (node?: OrgNode) => {
    const target = node || selectedNode;
    if (!target || target.type === 'team') return;

    const removeNodeFn = (tree: OrgNode, id: string): OrgNode => {
      return {
        ...tree,
        children: tree.children
          .filter((child) => child.id !== id)
          .map((child) => removeNodeFn(child, id)),
      };
    };
    const newTree = removeNodeFn(orgTree, target.id);
    setOrgTree(newTree);
    setSelectedNode(null);
    void persistTree(newTree);
  };

  const handleAddNode = () => {
    if (!selectedNode || selectedNode.type === 'agent') return;

    const newNode: OrgNode = {
      id: `node-${Date.now()}`,
      name: addForm.name,
      description: addForm.description,
      type: addForm.type,
      expanded: true,
      children: [],
    };

    const addToNode = (tree: OrgNode, targetId: string, node: OrgNode): OrgNode => {
      if (tree.id === targetId) {
        return { ...tree, children: [...tree.children, node], expanded: true };
      }
      return {
        ...tree,
        children: tree.children.map((child) => addToNode(child, targetId, node)),
      };
    };

    const newTree = addToNode(orgTree, selectedNode.id, newNode);
    setOrgTree(newTree);
    setShowAddDialog(false);
    setAddForm({ name: '', description: '', type: 'group' });
    void persistTree(newTree);
  };

  const countNodes = (node: OrgNode): { agents: number; groups: number } => {
    let agents = node.type === 'agent' ? 1 : 0;
    let groups = node.type === 'group' ? 1 : 0;
    for (const child of node.children) {
      const counts = countNodes(child);
      agents += counts.agents;
      groups += counts.groups;
    }
    return { agents, groups };
  };

  const totalCounts = countNodes(orgTree);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-surface p-6">
        <Card className="p-12 text-center">
          <RefreshCw className="w-10 h-10 text-slate mx-auto mb-4 animate-spin" />
          <h3 className="text-lg font-medium text-ink mb-2">正在加载组织架构</h3>
          <p className="text-sm text-slate">正在读取 Hermes Profile 组织树...</p>
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
              <h1 className="text-2xl font-semibold text-ink">组织架构</h1>
              <p className="text-sm text-slate mt-1">
                管理多智能体系统的组织层级，支持拖拽调整Agent归属
              </p>
            </div>
            <div className="flex items-center gap-3">
              {isSaving && <span className="text-xs text-slate">正在保存...</span>}
              <Badge variant="soft" color="purple">
                <Users className="w-3 h-3 mr-1" />
                {totalCounts.agents} 个Agent
              </Badge>
              <Badge variant="soft" color="blue">
                <GitBranch className="w-3 h-3 mr-1" />
                {totalCounts.groups} 个小组
              </Badge>
              <Button variant="secondary" size="sm" onClick={() => {
                loadTree(false).catch((requestError) => {
                  setError(requestError instanceof Error ? requestError.message : '获取组织架构失败');
                });
              }} disabled={isRefreshing}>
                <RefreshCw className={`w-4 h-4 mr-1 ${isRefreshing ? 'animate-spin' : ''}`} />
                刷新
              </Button>
            </div>
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
          {/* Tree View */}
          <div className="flex-1">
            <Card className="p-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-ink">架构树</h3>
                <span className="text-xs text-slate">拖拽节点调整归属</span>
              </div>
              <TreeNode
                node={orgTree}
                level={0}
                selectedId={selectedNode?.id || null}
                onSelect={handleSelect}
                onToggle={handleToggle}
                onEdit={(node) => { handleSelect(node); startEditNode(node); }}
                onDelete={(node) => { handleSelect(node); deleteNode(node); }}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                dragNodeId={dragNodeId}
                dropTargetId={dropTargetId}
              />
            </Card>
          </div>

          {/* Detail Panel */}
          <div className="w-96 flex-shrink-0">
            {selectedNode ? (
              <Card className="p-6">
                {/* Node Header */}
                <div className="flex items-start justify-between mb-6">
                  <div className="flex items-center gap-3">
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${typeColors[selectedNode.type]}`}>
                      {typeIcons[selectedNode.type]}
                    </div>
                    <div>
                      <h3 className="font-semibold text-ink">{selectedNode.name}</h3>
                      <Badge variant="soft" color="slate">
                        {typeLabels[selectedNode.type]}
                      </Badge>
                    </div>
                  </div>
                  {selectedNode.type !== 'team' && (
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => startEditNode()}>
                        <Edit className="w-4 h-4" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => deleteNode()}>
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </Button>
                    </div>
                  )}
                </div>

                {/* Node Info */}
                {editingNode ? (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-ink mb-2">名称</label>
                      <Input
                        value={editForm.name || ''}
                        onChange={(e) => setEditForm(prev => ({ ...prev, name: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-ink mb-2">描述</label>
                      <Input
                        value={editForm.description || ''}
                        onChange={(e) => setEditForm(prev => ({ ...prev, description: e.target.value }))}
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button variant="ghost" size="sm" onClick={() => setEditingNode(false)}>
                        <X className="w-4 h-4 mr-1" />
                        取消
                      </Button>
                      <Button size="sm" onClick={saveEditNode}>
                        <Save className="w-4 h-4 mr-1" />
                        保存
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-xs text-slate mb-1">描述</label>
                      <p className="text-sm text-ink">{selectedNode.description}</p>
                    </div>

                    {selectedNode.type === 'agent' && selectedNode.agent_config && (
                      <>
                        <hr className="border-hairline" />
                        <h4 className="font-medium text-ink text-sm">Agent配置</h4>
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-slate">角色</span>
                            <Badge variant="soft" className={roleColors[selectedNode.agent_config.role]}>
                              {roleLabels[selectedNode.agent_config.role]}
                            </Badge>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-slate">模型</span>
                            <code className="text-xs bg-slate-100 px-2 py-0.5 rounded">
                              {selectedNode.agent_config.model}
                            </code>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-slate">Temperature</span>
                            <span className="text-sm text-ink">{selectedNode.agent_config.temperature}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-slate">工作目录</span>
                            <code className="text-xs bg-slate-100 px-2 py-0.5 rounded">
                              {selectedNode.agent_config.working_directory}
                            </code>
                          </div>
                        </div>
                        <Button
                          variant="secondary"
                          size="sm"
                          fullWidth
                          onClick={() => window.location.href = `/agents?id=${selectedNode.id}`}
                        >
                          <Settings className="w-4 h-4 mr-1" />
                          查看完整配置
                        </Button>
                      </>
                    )}

                    {selectedNode.type !== 'agent' && (
                      <>
                        <hr className="border-hairline" />
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-slate">子节点数</span>
                            <span className="text-sm text-ink font-medium">
                              {selectedNode.children.length}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-slate">包含Agent数</span>
                            <span className="text-sm text-ink font-medium">
                              {countNodes(selectedNode).agents}
                            </span>
                          </div>
                        </div>

                        <Button
                          size="sm"
                          fullWidth
                          onClick={() => setShowAddDialog(true)}
                        >
                          <UserPlus className="w-4 h-4 mr-1" />
                          添加子节点
                        </Button>
                      </>
                    )}
                  </div>
                )}

                {/* Add Dialog */}
                {showAddDialog && (
                  <div className="mt-6 pt-6 border-t border-hairline">
                    <h4 className="font-medium text-ink mb-4">添加新节点</h4>
                    <div className="space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-ink mb-2">节点类型</label>
                        <div className="flex gap-2">
                          <Button
                            variant={addForm.type === 'group' ? 'default' : 'ghost'}
                            size="sm"
                            onClick={() => setAddForm(prev => ({ ...prev, type: 'group' }))}
                          >
                            <GitBranch className="w-4 h-4 mr-1" />
                            小组
                          </Button>
                          <Button
                            variant={addForm.type === 'agent' ? 'default' : 'ghost'}
                            size="sm"
                            onClick={() => setAddForm(prev => ({ ...prev, type: 'agent' }))}
                          >
                            <Bot className="w-4 h-4 mr-1" />
                            Agent
                          </Button>
                        </div>
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-ink mb-2">名称</label>
                        <Input
                          value={addForm.name}
                          onChange={(e) => setAddForm(prev => ({ ...prev, name: e.target.value }))}
                          placeholder="输入节点名称"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-ink mb-2">描述</label>
                        <Input
                          value={addForm.description}
                          onChange={(e) => setAddForm(prev => ({ ...prev, description: e.target.value }))}
                          placeholder="输入节点描述"
                        />
                      </div>
                      <div className="flex gap-2">
                        <Button variant="ghost" size="sm" fullWidth onClick={() => setShowAddDialog(false)}>
                          取消
                        </Button>
                        <Button size="sm" fullWidth onClick={handleAddNode} disabled={!addForm.name}>
                          <Plus className="w-4 h-4 mr-1" />
                          添加
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </Card>
            ) : (
              <Card className="p-12 text-center">
                <GitBranch className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                <p className="text-slate-500">选择一个节点查看详情</p>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
