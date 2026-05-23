'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  AlertTriangle,
  CheckCircle,
  Download,
  Eye,
  FileText,
  Lightbulb,
  RefreshCw,
  RotateCcw,
  Send,
  Shield,
  Zap,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs';
import { CodeBlock } from '@/components/ui/CodeBlock';
import { workflowApi, type WorkflowResponse } from '@/lib/api';

type Severity = 'critical' | 'high' | 'medium' | 'low';

interface ReviewIssue {
  severity: Severity;
  location: string;
  description: string;
  suggestion: string;
}

interface ScoreItem {
  score: number;
  label: string;
}

const terminalLabels: Record<string, string> = {
  completed: '专利申请已完成',
  failed: '专利申请已终止',
  cancelled: '专利申请已取消',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function ratingToScore(rating: unknown): ScoreItem {
  switch (rating) {
    case 'high':
      return { score: 90, label: '高' };
    case 'medium':
      return { score: 70, label: '中' };
    case 'low':
      return { score: 45, label: '低' };
    default:
      return { score: 0, label: '待评估' };
  }
}

function normalizeScore(value: unknown): number | null {
  const score = numberValue(value);
  if (score === null) return null;
  return Math.round(score <= 1 ? score * 100 : score);
}

function getNestedRecord(record: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = record[key];
  return isRecord(value) ? value : {};
}

function getPatentScores(workflow: WorkflowResponse | null) {
  const retrievalReport = workflow?.outputs.retrieval_report ?? {};
  const reviewReport = workflow?.outputs.review_report ?? {};
  const novelty = ratingToScore(getNestedRecord(retrievalReport, 'novelty_assessment').rating);
  const inventiveness = ratingToScore(getNestedRecord(retrievalReport, 'inventive_step_assessment').rating);
  const practicality = ratingToScore(getNestedRecord(retrievalReport, 'utility_assessment').rating);
  const reviewScore = normalizeScore(reviewReport.overall_score);
  const overall = reviewScore ?? ratingToScore(retrievalReport.overall_patentability).score;

  return {
    overallScore: overall,
    novelty,
    inventiveness,
    practicality,
  };
}

function getDraftText(workflow: WorkflowResponse | null) {
  const draft = workflow?.outputs.patent_draft ?? {};
  const claims = getNestedRecord(draft, 'claims');
  const description = getNestedRecord(draft, 'description');
  const dependentClaims = arrayValue(claims.dependent_claims)
    .map((claim) => stringValue(claim))
    .filter(Boolean);

  return {
    claims: [stringValue(claims.independent_claim), ...dependentClaims].filter(Boolean).join('\n\n'),
    description: Object.entries(description)
      .map(([key, value]) => `${key}\n${stringValue(value)}`)
      .filter((section) => !section.endsWith('\n'))
      .join('\n\n'),
    abstract: stringValue(draft.abstract),
  };
}

function parseIssues(value: unknown): ReviewIssue[] {
  return arrayValue(value)
    .filter(isRecord)
    .map((issue) => ({
      severity: ['critical', 'high', 'medium', 'low'].includes(stringValue(issue.severity))
        ? stringValue(issue.severity) as Severity
        : 'medium',
      location: stringValue(issue.location, '未指定位置'),
      description: stringValue(issue.description, '未提供问题描述'),
      suggestion: stringValue(issue.suggestion, '请补充审查建议'),
    }));
}

function getReviewIssues(workflow: WorkflowResponse | null): ReviewIssue[] {
  const review = workflow?.outputs.review_report ?? {};
  return [
    ...parseIssues(getNestedRecord(review, 'formal_compliance').issues),
    ...parseIssues(getNestedRecord(review, 'claims_review').issues),
    ...parseIssues(getNestedRecord(review, 'description_review').issues),
    ...parseIssues(getNestedRecord(review, 'consistency_review').issues),
  ];
}

function getInnovationPoints(workflow: WorkflowResponse | null): string[] {
  const requirement = workflow?.outputs.requirement_analysis ?? {};
  const features = arrayValue(requirement.key_features)
    .filter(isRecord)
    .map((feature) => stringValue(feature.description || feature.name))
    .filter(Boolean);

  if (features.length > 0) return features;

  return arrayValue(requirement.beneficial_effects)
    .map((effect) => stringValue(effect))
    .filter(Boolean);
}

function getRiskSuggestions(workflow: WorkflowResponse | null): string[] {
  const retrieval = workflow?.outputs.retrieval_report ?? {};
  const review = workflow?.outputs.review_report ?? {};
  const examinationRisks = arrayValue(review.examination_risks)
    .filter(isRecord)
    .map((risk) => stringValue(risk.mitigation_suggestion || risk.risk_type))
    .filter(Boolean);
  const riskFactors = arrayValue(retrieval.risk_factors)
    .map((risk) => stringValue(risk))
    .filter(Boolean);

  return [...examinationRisks, ...riskFactors];
}

function downloadText(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function getSeverityColor(severity: string) {
  switch (severity) {
    case 'critical':
      return 'text-red-500 bg-red-50';
    case 'high':
      return 'text-accent-orange bg-orange-50';
    case 'medium':
      return 'text-yellow-600 bg-yellow-50';
    default:
      return 'text-steel bg-hairline-soft';
  }
}

function getScoreColor(score: number) {
  if (score >= 80) return 'text-brand-green-dark';
  if (score >= 60) return 'text-accent-orange';
  return score > 0 ? 'text-red-500' : 'text-muted';
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-center py-xxl text-muted">
      <FileText className="w-12 h-12 mx-auto mb-md opacity-50" />
      <p>{message}</p>
    </div>
  );
}

export default function ResultPage() {
  const params = useParams();
  const router = useRouter();
  const taskId = params.taskId as string;
  const [activeTab, setActiveTab] = useState('overview');
  const [workflow, setWorkflow] = useState<WorkflowResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scores = useMemo(() => getPatentScores(workflow), [workflow]);
  const draft = useMemo(() => getDraftText(workflow), [workflow]);
  const reviewIssues = useMemo(() => getReviewIssues(workflow), [workflow]);
  const innovationPoints = useMemo(() => getInnovationPoints(workflow), [workflow]);
  const riskSuggestions = useMemo(() => getRiskSuggestions(workflow), [workflow]);
  const title = terminalLabels[workflow?.current_state ?? ''] ?? '专利申请结果';
  const isCompleted = workflow?.current_state === 'completed';
  const hasDraft = Boolean(draft.claims || draft.description || draft.abstract);

  const loadResult = useCallback(async (showLoading = false) => {
    if (showLoading) {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    try {
      const data = await workflowApi.get(taskId);
      setWorkflow(data);
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '获取专利结果失败');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [taskId]);

  useEffect(() => {
    loadResult(true).catch((requestError) => {
      setError(requestError instanceof Error ? requestError.message : '获取专利结果失败');
    });
  }, [loadResult]);

  const downloadPackage = () => {
    if (!workflow) return;
    downloadText(
      `${taskId}-patent-package.json`,
      JSON.stringify({
        task_id: workflow.task_id,
        scores,
        requirement_analysis: workflow.outputs.requirement_analysis,
        retrieval_report: workflow.outputs.retrieval_report,
        patent_draft: workflow.outputs.patent_draft,
        review_report: workflow.outputs.review_report,
      }, null, 2)
    );
  };

  return (
    <div className="py-section-lg bg-surface min-h-screen">
      <div className="container mx-auto px-md">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-md mb-xl">
          <div>
            <div className="flex items-center gap-md mb-xs">
              {isCompleted ? (
                <CheckCircle className="w-8 h-8 text-brand-green-dark" />
              ) : (
                <Eye className="w-8 h-8 text-brand-green-dark" />
              )}
              <h1 className="text-heading-2 font-euclid font-medium text-ink">
                {title}
              </h1>
            </div>
            <p className="text-body-md text-steel">
              任务 ID: {taskId} · {isCompleted ? '所有 Agent 工作已完成' : '当前结果来自已完成阶段'}
            </p>
          </div>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => router.push('/')}>
              <RotateCcw className="w-4 h-4 mr-2" />
              新申请
            </Button>
            <Button variant="secondary" onClick={() => router.push(`/workflow/${taskId}`)}>
              <Eye className="w-4 h-4 mr-2" />
              查看流程
            </Button>
            <Button onClick={downloadPackage} disabled={!workflow}>
              <Download className="w-4 h-4 mr-2" />
              下载全部文件
            </Button>
          </div>
        </div>

        {error && (
          <Card className="mb-xl border-red-200 bg-red-50">
            <CardContent className="pt-lg">
              <div className="flex items-center justify-between gap-md text-red-700">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5" />
                  <span className="text-body-sm-medium">{error}</span>
                </div>
                <Button variant="ghost" size="sm" onClick={() => loadResult(false)} disabled={isRefreshing}>
                  <RefreshCw className={`w-4 h-4 mr-1 ${isRefreshing ? 'animate-spin' : ''}`} />
                  重试
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {isLoading ? (
          <Card>
            <CardContent className="py-xxl text-center text-muted">
              <RefreshCw className="w-8 h-8 mx-auto mb-md animate-spin" />
              <p>正在加载专利结果...</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid lg:grid-cols-4 gap-xl">
            <div className="lg:col-span-1 space-y-lg">
              <Card variant="feature">
                <CardHeader>
                  <CardTitle className="text-center">专利性评分</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-center mb-xl">
                    <div className="relative w-32 h-32 mx-auto">
                      <svg className="w-full h-full transform -rotate-90">
                        <circle cx="64" cy="64" r="56" stroke="#e1e5e8" strokeWidth="8" fill="none" />
                        <circle
                          cx="64"
                          cy="64"
                          r="56"
                          stroke="#00ed64"
                          strokeWidth="8"
                          fill="none"
                          strokeDasharray={`${(scores.overallScore / 100) * 352} 352`}
                          strokeLinecap="round"
                        />
                      </svg>
                      <div className="absolute inset-0 flex items-center justify-center">
                        <span className="text-display-lg font-euclid font-semibold text-brand-green-dark">
                          {scores.overallScore || '--'}
                        </span>
                      </div>
                    </div>
                    <p className="text-body-sm text-steel mt-md">综合专利性指数</p>
                  </div>

                  <div className="space-y-md">
                    {[
                      { icon: Zap, name: '新颖性', ...scores.novelty },
                      { icon: Lightbulb, name: '创造性', ...scores.inventiveness },
                      { icon: Shield, name: '实用性', ...scores.practicality },
                    ].map((item) => {
                      const Icon = item.icon;
                      return (
                        <div key={item.name} className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Icon className="w-4 h-4 text-steel" />
                            <span className="text-body-sm text-ink">{item.name}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className={`text-body-sm-medium font-medium ${getScoreColor(item.score)}`}>
                              {item.score ? `${item.score}分` : '--'}
                            </span>
                            <Badge variant="green-soft">{item.label}</Badge>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-heading-5">快捷操作</CardTitle>
                </CardHeader>
                <CardContent className="space-y-md">
                  <Button variant="secondary" fullWidth onClick={() => setActiveTab('review')}>
                    <FileText className="w-4 h-4 mr-2" />
                    查看完整分析报告
                  </Button>
                  <Button variant="secondary" fullWidth>
                    <Send className="w-4 h-4 mr-2" />
                    提交人工审核
                  </Button>
                  <Button variant="ghost" fullWidth onClick={() => navigator.clipboard.writeText(window.location.href)}>
                    分享此页面
                  </Button>
                </CardContent>
              </Card>
            </div>

            <div className="lg:col-span-3 space-y-lg">
              <Card>
                <CardContent className="pt-lg">
                  <Tabs value={activeTab} onValueChange={setActiveTab}>
                    <TabsList variant="segmented">
                      <TabsTrigger value="overview">概览</TabsTrigger>
                      <TabsTrigger value="claims">权利要求书</TabsTrigger>
                      <TabsTrigger value="description">说明书</TabsTrigger>
                      <TabsTrigger value="review">审查意见</TabsTrigger>
                    </TabsList>

                    <TabsContent value="overview">
                      <div className="grid md:grid-cols-2 gap-xl">
                        <div>
                          <h3 className="text-heading-5 font-euclid font-medium text-ink mb-md">
                            核心创新点
                          </h3>
                          {innovationPoints.length > 0 ? (
                            <ul className="space-y-md">
                              {innovationPoints.map((point, index) => (
                                <li key={point} className="flex items-start gap-2">
                                  <span className="w-5 h-5 rounded-full bg-surface-feature text-brand-green-dark text-micro font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                                    {index + 1}
                                  </span>
                                  <span className="text-body-md text-steel">{point}</span>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <EmptyState message="暂无结构化创新点，请等待需求分析完成。" />
                          )}
                        </div>
                        <div>
                          <h3 className="text-heading-5 font-euclid font-medium text-ink mb-md">
                            风险提示
                          </h3>
                          <div className="space-y-md">
                            {reviewIssues.length > 0 ? reviewIssues.slice(0, 3).map((issue) => (
                              <div key={`${issue.location}-${issue.description}`} className={`p-md rounded-lg ${getSeverityColor(issue.severity)}`}>
                                <div className="flex items-start gap-2">
                                  <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                                  <div>
                                    <p className="text-body-sm-medium font-medium mb-xs">{issue.location}</p>
                                    <p className="text-body-sm">{issue.description}</p>
                                    <p className="text-caption mt-xs opacity-80">建议：{issue.suggestion}</p>
                                  </div>
                                </div>
                              </div>
                            )) : (
                              <Card className="bg-surface-feature border-none">
                                <CardContent className="py-md text-body-sm text-brand-green-dark">
                                  暂无审查问题。
                                </CardContent>
                              </Card>
                            )}
                          </div>
                        </div>
                      </div>
                    </TabsContent>

                    <TabsContent value="claims">
                      <div className="mb-md flex justify-between items-center">
                        <h3 className="text-heading-5 font-euclid font-medium text-ink">权利要求书</h3>
                        <Button variant="ghost" size="sm" onClick={() => downloadText(`${taskId}-claims.txt`, draft.claims)} disabled={!draft.claims}>
                          <Download className="w-4 h-4 mr-1" />
                          下载
                        </Button>
                      </div>
                      {draft.claims ? <CodeBlock language="text">{draft.claims}</CodeBlock> : <EmptyState message="权利要求书尚未生成。" />}
                    </TabsContent>

                    <TabsContent value="description">
                      <div className="mb-md flex justify-between items-center">
                        <h3 className="text-heading-5 font-euclid font-medium text-ink">专利说明书</h3>
                        <Button variant="ghost" size="sm" onClick={() => downloadText(`${taskId}-description.txt`, draft.description)} disabled={!draft.description}>
                          <Download className="w-4 h-4 mr-1" />
                          下载
                        </Button>
                      </div>
                      {draft.description ? <CodeBlock language="text">{draft.description}</CodeBlock> : <EmptyState message="专利说明书尚未生成。" />}
                    </TabsContent>

                    <TabsContent value="review">
                      <h3 className="text-heading-5 font-euclid font-medium text-ink mb-md">质量审查报告</h3>
                      <div className="space-y-lg">
                        <div>
                          <h4 className="text-body-md-medium font-medium text-ink mb-md flex items-center gap-2">
                            <CheckCircle className="w-5 h-5 text-brand-green-dark" />
                            形式合规性检查
                          </h4>
                          <Card className="bg-surface-feature border-none">
                            <CardContent className="py-md">
                              <p className="text-body-sm text-brand-green-dark">
                                {reviewIssues.length === 0 ? '未发现格式或一致性问题。' : `发现 ${reviewIssues.length} 项需关注问题。`}
                              </p>
                            </CardContent>
                          </Card>
                        </div>

                        <div>
                          <h4 className="text-body-md-medium font-medium text-ink mb-md flex items-center gap-2">
                            <AlertTriangle className="w-5 h-5 text-accent-orange" />
                            实质审查意见
                          </h4>
                          <div className="space-y-md">
                            {reviewIssues.length > 0 ? reviewIssues.map((issue) => (
                              <div key={`${issue.location}-${issue.description}`} className={`p-lg rounded-lg border ${getSeverityColor(issue.severity)} border-opacity-50`}>
                                <div className="flex items-start justify-between mb-md">
                                  <Badge variant={issue.severity === 'critical' || issue.severity === 'high' ? 'orange' : 'gray'}>
                                    {issue.severity === 'critical' ? '严重' : issue.severity === 'high' ? '高' : issue.severity === 'medium' ? '中' : '低'}
                                  </Badge>
                                  <span className="text-body-sm text-muted">{issue.location}</span>
                                </div>
                                <p className="text-body-md text-ink mb-sm">{issue.description}</p>
                                <p className="text-body-sm text-steel"><strong>优化建议：</strong>{issue.suggestion}</p>
                              </div>
                            )) : <EmptyState message="暂无实质审查意见。" />}
                          </div>
                        </div>

                        <div>
                          <h4 className="text-body-md-medium font-medium text-ink mb-md flex items-center gap-2">
                            <Lightbulb className="w-5 h-5 text-brand-green-dark" />
                            审查风险预判
                          </h4>
                          <Card>
                            <CardContent className="py-md">
                              {riskSuggestions.length > 0 ? (
                                <ul className="space-y-sm">
                                  {riskSuggestions.map((suggestion) => (
                                    <li key={suggestion} className="text-body-sm text-steel flex items-start gap-2">
                                      <span className="text-brand-green-dark">•</span>
                                      {suggestion}
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="text-body-sm text-steel">暂无额外风险预判。</p>
                              )}
                            </CardContent>
                          </Card>
                        </div>
                      </div>
                    </TabsContent>
                  </Tabs>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>文件下载</CardTitle>
                  <CardDescription>下载生成的专利申请文件和结构化分析报告</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid md:grid-cols-3 gap-md">
                    {[
                      { name: '权利要求书', format: 'TXT', content: draft.claims, filename: `${taskId}-claims.txt` },
                      { name: '专利说明书', format: 'TXT', content: draft.description, filename: `${taskId}-description.txt` },
                      { name: '完整申请包', format: 'JSON', content: workflow ? JSON.stringify(workflow.outputs, null, 2) : '', filename: `${taskId}-outputs.json` },
                    ].map((file) => (
                      <div key={file.name} className="flex items-center justify-between p-md rounded-lg border border-hairline hover:border-stone transition-colors">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg bg-surface-feature flex items-center justify-center">
                            <FileText className="w-5 h-5 text-brand-green-dark" />
                          </div>
                          <div>
                            <p className="text-body-sm-medium font-medium text-ink">{file.name}</p>
                            <p className="text-caption text-muted">{file.format}</p>
                          </div>
                        </div>
                        <Button variant="ghost" size="sm" onClick={() => downloadText(file.filename, file.content)} disabled={!file.content}>
                          <Download className="w-4 h-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                </CardContent>
                <CardFooter className="border-t border-hairline flex justify-between pt-lg">
                  <p className="text-body-sm text-muted">
                    {hasDraft ? '已生成可下载申请文件' : '申请文件尚未生成'}
                  </p>
                  <Button onClick={downloadPackage} disabled={!workflow}>
                    <Download className="w-4 h-4 mr-2" />
                    下载全部
                  </Button>
                </CardFooter>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
