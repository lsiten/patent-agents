'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Plus,
  Search,
  FileText,
  Eye,
  MessageSquare,
  Download,
  Filter,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader,
  Sparkles,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { clsx } from 'clsx';
import { workflowApi, type WorkflowResponse } from '@/lib/api';
import type { PatentSummary, WorkflowState } from '@/types';

const stateMap: Record<string, WorkflowState> = {
  initialized: 'initial',
  brainstorming: 'initial',
  requirement_analysis: 'requirement',
  retrieval_analysis: 'retrieval',
  patent_writing: 'writing',
  quality_review: 'reviewing',
  iteration: 'iteration',
  completed: 'completed',
  failed: 'failed',
  cancelled: 'failed',
};

const progressMap: Record<WorkflowState, number> = {
  initial: 5,
  requirement: 25,
  retrieval: 45,
  writing: 65,
  reviewing: 85,
  iteration: 90,
  completed: 100,
  failed: 45,
};

const stateLabels: Record<WorkflowState, string> = {
  initial: '头脑风暴中',
  requirement: '需求分析中',
  retrieval: '检索分析中',
  writing: '撰写中',
  reviewing: '质量审查中',
  iteration: '迭代优化中',
  completed: '已完成',
  failed: '已终止',
};

const stateColors: Record<WorkflowState, string> = {
  initial: 'bg-slate-100 text-slate-600',
  requirement: 'bg-blue-100 text-blue-700',
  retrieval: 'bg-purple-100 text-purple-700',
  writing: 'bg-yellow-100 text-yellow-700',
  reviewing: 'bg-orange-100 text-orange-700',
  iteration: 'bg-cyan-100 text-cyan-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
};

const stateIcons: Record<WorkflowState, React.ReactNode> = {
  initial: <Clock className="w-4 h-4" />,
  requirement: <FileText className="w-4 h-4" />,
  retrieval: <Search className="w-4 h-4" />,
  writing: <FileText className="w-4 h-4" />,
  reviewing: <Eye className="w-4 h-4" />,
  iteration: <Loader className="w-4 h-4" />,
  completed: <CheckCircle2 className="w-4 h-4" />,
  failed: <AlertCircle className="w-4 h-4" />,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function getNestedRecord(record: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = record[key];
  return isRecord(value) ? value : {};
}

function workflowStateToPatentState(state: string): WorkflowState {
  return stateMap[state] ?? 'initial';
}

function getWorkflowTitle(workflow: WorkflowResponse): string {
  const requirement = workflow.outputs.requirement_analysis;
  const brainstorming = workflow.outputs.brainstorming;
  const field = stringValue(requirement['tech_field'] || brainstorming['tech_field']);
  const problem = stringValue(requirement['technical_problem'] || brainstorming['technical_problem']);

  if (field && problem) return `${field}：${problem.slice(0, 28)}`;
  if (field) return field;
  return `专利申请 ${workflow.task_id.slice(0, 8)}`;
}

function getTechField(workflow: WorkflowResponse): string {
  const requirement = workflow.outputs.requirement_analysis;
  const brainstorming = workflow.outputs.brainstorming;
  return stringValue(requirement.tech_field || brainstorming.tech_field, '待分析');
}

function getPatentType(workflow: WorkflowResponse): PatentSummary['patent_type'] {
  const recommendation = getNestedRecord(workflow.outputs.requirement_analysis, 'patent_type_recommendation');
  const type = stringValue(recommendation['type']);
  return type === 'utility' || type === 'design' ? type : 'invention';
}

function workflowToPatentSummary(workflow: WorkflowResponse): PatentSummary {
  const currentState = workflowStateToPatentState(workflow.current_state);
  const inventors = arrayValue(workflow.outputs.brainstorming.inventors)
    .map((inventor) => stringValue(inventor))
    .filter(Boolean);

  return {
    task_id: workflow.task_id,
    title: getWorkflowTitle(workflow),
    patent_type: getPatentType(workflow),
    tech_field: getTechField(workflow),
    current_state: currentState,
    progress: progressMap[currentState],
    created_at: workflow.created_at,
    updated_at: workflow.updated_at ?? workflow.created_at,
    inventors: inventors.length > 0 ? inventors : undefined,
  };
}

function getProgressColor(progress: number) {
  if (progress >= 80) return 'bg-green-500';
  if (progress >= 50) return 'bg-yellow-500';
  return 'bg-blue-500';
}

export default function PatentsPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState('all');
  const [selectedPatent, setSelectedPatent] = useState<string | null>(null);
  const [patents, setPatents] = useState<PatentSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filters = [
    { id: 'all', label: '全部' },
    { id: 'in_progress', label: '进行中' },
    { id: 'completed', label: '已完成' },
    { id: 'failed', label: '已终止' },
  ];

  const loadPatents = useCallback(async (showLoading = false) => {
    if (showLoading) {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    try {
      const response = await workflowApi.list();
      setPatents(response.items.map(workflowToPatentSummary));
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '获取专利列表失败');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      await loadPatents(true);
    };

    load().catch((requestError) => {
      setError(requestError instanceof Error ? requestError.message : '获取专利列表失败');
    });
  }, [loadPatents]);

  const filteredPatents = useMemo(() => patents.filter((patent) => {
    const normalizedSearch = searchQuery.toLowerCase();
    const matchesSearch =
      patent.title.toLowerCase().includes(normalizedSearch) ||
      patent.tech_field.toLowerCase().includes(normalizedSearch) ||
      patent.task_id.toLowerCase().includes(normalizedSearch);

    const matchesFilter =
      activeFilter === 'all' ||
      (activeFilter === 'in_progress' && !['completed', 'failed'].includes(patent.current_state)) ||
      (activeFilter === 'completed' && patent.current_state === 'completed') ||
      (activeFilter === 'failed' && patent.current_state === 'failed');

    return matchesSearch && matchesFilter;
  }), [activeFilter, patents, searchQuery]);

  const inProgressCount = patents.filter((patent) => !['completed', 'failed'].includes(patent.current_state)).length;
  const completedCount = patents.filter((patent) => patent.current_state === 'completed').length;
  const currentMonthCount = patents.filter((patent) => {
    const createdAt = new Date(patent.created_at);
    const now = new Date();
    return createdAt.getFullYear() === now.getFullYear() && createdAt.getMonth() === now.getMonth();
  }).length;

  return (
    <div className="min-h-screen bg-surface">
      <div className="border-b border-hairline bg-canvas px-6 py-5">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-ink">专利管理</h1>
              <p className="text-sm text-slate mt-1">
                管理您的所有专利申请，查看进度，进入对话修改，下载专利文件
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Button variant="secondary" onClick={() => {
                  loadPatents(false).catch((requestError) => {
                    setError(requestError instanceof Error ? requestError.message : '获取专利列表失败');
                  });
                }} disabled={isRefreshing}>
                <RefreshCw className={`w-4 h-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
                刷新
              </Button>
              <Button onClick={() => window.location.href = '/'}>
                <Plus className="w-4 h-4 mr-2" />
                新建专利申请
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4 mt-6">
            <Card className="p-4">
              <p className="text-sm text-slate">总申请数</p>
              <p className="text-2xl font-bold text-ink mt-1">{patents.length}</p>
            </Card>
            <Card className="p-4">
              <p className="text-sm text-slate">进行中</p>
              <p className="text-2xl font-bold text-ink mt-1">{inProgressCount}</p>
            </Card>
            <Card className="p-4">
              <p className="text-sm text-slate">已完成</p>
              <p className="text-2xl font-bold text-green-600 mt-1">{completedCount}</p>
            </Card>
            <Card className="p-4">
              <p className="text-sm text-slate">本月新增</p>
              <p className="text-2xl font-bold text-blue-600 mt-1">{currentMonthCount}</p>
            </Card>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-5">
        {error && (
          <Card className="p-4 mb-5 border-red-200 bg-red-50">
            <div className="flex items-center justify-between gap-4 text-red-700">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-5 h-5" />
                <span className="text-sm font-medium">{error}</span>
              </div>
              <Button variant="ghost" size="sm" onClick={() => {
                  loadPatents(false).catch((requestError) => {
                    setError(requestError instanceof Error ? requestError.message : '获取专利列表失败');
                  });
                }} disabled={isRefreshing}>
                重试
              </Button>
            </div>
          </Card>
        )}

        <div className="flex items-center justify-between mb-5">
          <Tabs value={activeFilter} onValueChange={setActiveFilter}>
            <TabsList>
              {filters.map((filter) => (
                <TabsTrigger key={filter.id} value={filter.id}>
                  {filter.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <div className="flex items-center gap-3">
            <Input
              placeholder="搜索专利..."
              icon={<Search className="w-4 h-4" />}
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              className="w-64"
            />
            <Button variant="ghost" size="sm">
              <Filter className="w-4 h-4 mr-1" />
              高级筛选
            </Button>
          </div>
        </div>

        <div className="space-y-4">
          {isLoading ? (
            <Card className="p-12 text-center">
              <RefreshCw className="w-10 h-10 text-slate mx-auto mb-4 animate-spin" />
              <h3 className="text-lg font-medium text-ink mb-2">正在加载专利申请</h3>
              <p className="text-sm text-slate">请稍候...</p>
            </Card>
          ) : filteredPatents.length > 0 ? filteredPatents.map((patent) => (
            <Card
              key={patent.task_id}
              className={clsx(
                'p-5 transition-all duration-200 hover:shadow-md cursor-pointer',
                selectedPatent === patent.task_id && 'ring-2 ring-brand-green'
              )}
              onClick={() => setSelectedPatent((selected) => selected === patent.task_id ? null : patent.task_id)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-lg font-semibold text-ink">{patent.title}</h3>
                    <Badge variant="soft" className={clsx(stateColors[patent.current_state])}>
                      <span className="flex items-center gap-1.5">
                        {stateIcons[patent.current_state]}
                        {stateLabels[patent.current_state]}
                      </span>
                    </Badge>
                    <Badge variant="soft" color="blue">
                      {patent.patent_type === 'invention'
                        ? '发明专利'
                        : patent.patent_type === 'utility'
                        ? '实用新型'
                        : '外观设计'}
                    </Badge>
                  </div>

                  <p className="text-sm text-slate mb-3">{patent.tech_field}</p>

                  <div className="mb-4">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-slate">完成进度</span>
                      <span className="text-xs font-medium text-ink">{patent.progress}%</span>
                    </div>
                    <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className={clsx('h-full rounded-full transition-all duration-500', getProgressColor(patent.progress))}
                        style={{ width: `${patent.progress}%` }}
                      />
                    </div>
                  </div>

                  <div className="flex items-center gap-6 text-xs text-slate">
                    <span>编号：{patent.task_id}</span>
                    {patent.application_number && <span>申请号：{patent.application_number}</span>}
                    <span>创建时间：{new Date(patent.created_at).toLocaleDateString('zh-CN')}</span>
                    <span>更新时间：{new Date(patent.updated_at).toLocaleDateString('zh-CN')}</span>
                  </div>
                </div>

                <div className="flex flex-col gap-2 ml-6">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={(event) => {
                      event.stopPropagation();
                      window.location.href = `/chat?task_id=${patent.task_id}`;
                    }}
                  >
                    <MessageSquare className="w-4 h-4 mr-1.5" />
                    继续对话
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(event) => {
                      event.stopPropagation();
                      window.location.href = `/workflow/${patent.task_id}`;
                    }}
                  >
                    <Sparkles className="w-4 h-4 mr-1.5" />
                    查看进度
                  </Button>
                  {patent.current_state === 'completed' && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(event) => {
                        event.stopPropagation();
                        window.location.href = `/result/${patent.task_id}`;
                      }}
                    >
                      <Download className="w-4 h-4 mr-1.5" />
                      下载文件
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(event) => {
                      event.stopPropagation();
                      window.location.href = `/result/${patent.task_id}`;
                    }}
                  >
                    <Eye className="w-4 h-4 mr-1.5" />
                    查看详情
                  </Button>
                </div>
              </div>

              {selectedPatent === patent.task_id && (
                <div className="mt-5 pt-5 border-t border-hairline">
                  <div className="grid grid-cols-3 gap-6">
                    <div>
                      <h4 className="text-sm font-medium text-ink mb-3">发明人信息</h4>
                      <p className="text-sm text-slate">{patent.inventors ? patent.inventors.join('、') : '待定'}</p>
                    </div>
                    <div>
                      <h4 className="text-sm font-medium text-ink mb-3">申请人</h4>
                      <p className="text-sm text-slate">{patent.assignee || '待定'}</p>
                    </div>
                    <div>
                      <h4 className="text-sm font-medium text-ink mb-3">申请日期</h4>
                      <p className="text-sm text-slate">{patent.filing_date || '暂未提交'}</p>
                    </div>
                  </div>

                  <div className="mt-5 flex items-center gap-3">
                    <span className="text-sm text-slate mr-2">快捷操作：</span>
                    <Button variant="ghost" size="sm" onClick={() => window.location.href = `/workflow/${patent.task_id}`}>
                      <FileText className="w-4 h-4 mr-1.5" />
                      查看阶段输出
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => window.location.href = `/result/${patent.task_id}`}>
                      <Search className="w-4 h-4 mr-1.5" />
                      查看分析结果
                    </Button>
                    {patent.progress >= 60 && (
                      <Button variant="ghost" size="sm" onClick={() => window.location.href = `/result/${patent.task_id}`}>
                        <FileText className="w-4 h-4 mr-1.5" />
                        查看专利草稿
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </Card>
          )) : (
            <Card className="p-12 text-center">
              <FileText className="w-12 h-12 text-slate mx-auto mb-4" />
              <h3 className="text-lg font-medium text-ink mb-2">暂无专利申请</h3>
              <p className="text-sm text-slate mb-4">开始您的第一个专利申请吧</p>
              <Button onClick={() => window.location.href = '/'}>
                <Plus className="w-4 h-4 mr-2" />
                新建专利申请
              </Button>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
