'use client';

/**
 * Agent Output Renderers — 可视化展示每个 Agent 的输出结果
 *
 * 每个 Agent 输出对应一个专用渲染器:
 * - RequirementAnalysisView: 需求分析结果（技术领域/创新点/应用场景等）
 * - RetrievalReportView: 检索报告（专利性评分/风险因素/来源分析）
 * - PatentDraftView: 申请文件（文件列表/预览/下载）
 * - QualityReviewView: 审查意见（评分/问题列表/修改建议）
 */

import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Download,
  FileText,
  Lightbulb,
  Search,
  Shield,
  Star,
  Zap,
} from 'lucide-react';
import { useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { workflowApi } from '@/lib/api';
import { normalizeQualityScoreForDisplay } from '@/lib/quality-review-score';
import { getRetrievalPatentReferences } from '@/lib/retrieval-report';
import type { PatentDrawing } from '@/types';

// ─── Utilities ──────────────────────────────────────────────────────────────

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function str(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function arr(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function ratingBadge(rating: unknown) {
  const r = str(rating);
  const config: Record<string, { label: string; variant: 'green' | 'orange' | 'gray' }> = {
    high: { label: '高', variant: 'green' },
    medium: { label: '中', variant: 'orange' },
    low: { label: '低', variant: 'gray' },
  };
  const c = config[r] || { label: r || '未知', variant: 'gray' as const };
  return <Badge variant={c.variant}>{c.label}</Badge>;
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

function normalizePatentDrawing(value: unknown, taskId: string): PatentDrawing | null {
  if (!isRecord(value)) {
    return null;
  }

  const figureNumber = str(value.figure_number || value.figureNumber).trim();
  const title = str(value.title).trim();
  const description = str(value.description).trim();
  const artifactPathOrUrl = str(value.artifact_url || value.artifactUrl).trim();
  const artifactUrl = artifactPathOrUrl ? workflowApi.artifactUrl(taskId, artifactPathOrUrl) : '';

  if (!figureNumber && !title && !description && !artifactUrl) {
    return null;
  }

  return {
    figure_number: figureNumber,
    ...(title ? { title } : {}),
    ...(description ? { description } : {}),
    ...(str(value.file_path).trim() ? { file_path: str(value.file_path).trim() } : {}),
    ...(artifactUrl ? { artifact_url: artifactUrl } : {}),
    ...(str(value.mime_type).trim() ? { mime_type: str(value.mime_type).trim() } : {}),
  };
}

function drawingAltText(drawing: PatentDrawing): string {
  return [drawing.figure_number, drawing.title, drawing.description]
    .filter((part): part is string => Boolean(part))
    .join('，');
}

// ─── 1. 需求分析视图 ────────────────────────────────────────────────────────

interface RequirementAnalysisViewProps {
  data: Record<string, unknown>;
}

export function RequirementAnalysisView({ data }: RequirementAnalysisViewProps) {
  if (!data || Object.keys(data).length === 0) return null;

  const techField = str(data.tech_field);
  const corePrinciple = str(data.core_principle);
  const technicalProblem = str(data.technical_problem);
  const beneficialEffects = arr(data.beneficial_effects).map((e) => str(e)).filter(Boolean);
  const features = arr(data.key_innovative_features).filter(isRecord);
  const scenarios = arr(data.application_scenarios).map((s) => str(s)).filter(Boolean);
  const patentType = isRecord(data.patent_type_recommendation) ? data.patent_type_recommendation : {};
  const gaps = arr(data.information_gaps).map((g) => str(g)).filter(Boolean);

  return (
    <div className="space-y-lg">
      {/* 技术领域 */}
      <section>
        <h4 className="text-body-md-medium font-medium text-ink mb-sm flex items-center gap-2">
          <Search className="w-4 h-4 text-brand-green-dark" />
          技术领域
        </h4>
        <p className="text-body-md text-steel bg-surface-feature rounded-lg p-md">{techField || '待分析'}</p>
      </section>

      {/* 核心原理 */}
      {corePrinciple && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-brand-green-dark" />
            核心原理
          </h4>
          <p className="text-body-md text-steel bg-surface-feature rounded-lg p-md">{corePrinciple}</p>
        </section>
      )}

      {/* 技术问题 */}
      {technicalProblem && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-accent-orange" />
            要解决的技术问题
          </h4>
          <p className="text-body-md text-steel bg-surface-feature rounded-lg p-md">{technicalProblem}</p>
        </section>
      )}

      {/* 关键创新特征 */}
      {features.length > 0 && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm flex items-center gap-2">
            <Star className="w-4 h-4 text-brand-green-dark" />
            关键创新特征
          </h4>
          <div className="space-y-sm">
            {features.map((f, i) => (
              <div key={i} className="border border-hairline rounded-lg p-md">
                <div className="flex items-start gap-2">
                  <span className="w-6 h-6 rounded-full bg-brand-green text-ink text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                    {i + 1}
                  </span>
                  <div>
                    <p className="text-body-sm-medium font-medium text-ink">{str(f.name)}</p>
                    <p className="text-body-sm text-steel mt-xs">{str(f.description)}</p>
                    {str(f.technical_significance) && (
                      <p className="text-caption text-muted mt-xs">技术意义：{str(f.technical_significance)}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 应用场景 */}
      {scenarios.length > 0 && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm">应用场景</h4>
          <div className="flex flex-wrap gap-sm">
            {scenarios.map((s, i) => (
              <Badge key={i} variant="green-soft">{s}</Badge>
            ))}
          </div>
        </section>
      )}

      {/* 有益效果 */}
      {beneficialEffects.length > 0 && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm">有益效果</h4>
          <ul className="space-y-xs">
            {beneficialEffects.map((e, i) => (
              <li key={i} className="text-body-sm text-steel flex items-start gap-2">
                <CheckCircle className="w-4 h-4 text-brand-green-dark flex-shrink-0 mt-0.5" />
                {e}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* 专利类型推荐 */}
      {str(patentType.suggested_type) && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm">专利类型推荐</h4>
          <div className="bg-surface-feature rounded-lg p-md">
            <div className="flex items-center gap-2 mb-xs">
              <Badge variant="green">{str(patentType.suggested_type)}</Badge>
            </div>
            {str(patentType.rationale) && (
              <p className="text-body-sm text-steel">{str(patentType.rationale)}</p>
            )}
          </div>
        </section>
      )}

      {/* 信息缺口 */}
      {gaps.length > 0 && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-accent-orange" />
            待补充信息
          </h4>
          <ul className="space-y-xs">
            {gaps.map((g, i) => (
              <li key={i} className="text-body-sm text-steel flex items-start gap-2">
                <span className="text-accent-orange">•</span>
                {g}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// ─── 2. 检索报告视图 ────────────────────────────────────────────────────────

interface RetrievalReportViewProps {
  data: Record<string, unknown>;
}

export function RetrievalReportView({ data }: RetrievalReportViewProps) {
  if (!data || Object.keys(data).length === 0) return null;

  const [expandedRef, setExpandedRef] = useState<number | null>(null);

  // 尝试从 data.output 中解析 JSON 结构化数据
  // 后端返回的数据结构是 { agent, output, summary }，其中 output 可能是包含 JSON 的字符串
  let parsedData: Record<string, unknown> = data;
  if (typeof data.output === 'string') {
    // 尝试从 output 字符串中提取 JSON
    const jsonMatch = data.output.match(/\{[\s\S]*"retrieval_strategy"[\s\S]*\}/);
    if (jsonMatch) {
      try {
        parsedData = JSON.parse(jsonMatch[0]);
      } catch {
        // 解析失败，使用原始 data
      }
    }
  } else if (isRecord(data.output)) {
    // output 已经是对象
    parsedData = data.output as Record<string, unknown>;
  }

  // 从 retrieval_strategy 中提取关键词和数据源
  const retrievalStrategy = isRecord(parsedData.retrieval_strategy) ? parsedData.retrieval_strategy : {};
  const retrievalKeywords = arr(retrievalStrategy.keywords || parsedData.retrieval_keywords).map((k) => str(k)).filter(Boolean);
  const retrievalDatabases = arr(retrievalStrategy.databases_used || parsedData.retrieval_databases).map((d) => str(d)).filter(Boolean);

  const novelty = isRecord(parsedData.novelty_assessment) ? parsedData.novelty_assessment : {};
  const inventiveStep = isRecord(parsedData.inventive_step_assessment) ? parsedData.inventive_step_assessment : {};
  const utility = isRecord(parsedData.utility_assessment) ? parsedData.utility_assessment : {};
  const overallPatentability = str(parsedData.overall_patentability);
  const conclusion = str(parsedData.conclusion);
  const riskFactors = arr(parsedData.risk_factors).filter(isRecord);
  const recommendations = arr(parsedData.writing_recommendations).map((r) => str(r)).filter(Boolean);

  const priorArtReferences = getRetrievalPatentReferences(parsedData);

  const ratingScore = (rating: unknown) => {
    switch (str(rating)) {
      case 'high': return 90;
      case 'medium': return 70;
      case 'low': return 45;
      default: return 0;
    }
  };

  const dbDisplayName: Record<string, string> = {
    'USPTO': '美国专利商标局',
    'EPO': '欧洲专利局',
    'CNIPA': '中国国家知识产权局',
    'Google Patents': 'Google 专利',
    'arXiv': 'arXiv 学术论文',
    'uspto': '美国专利商标局',
    'epo': '欧洲专利局',
    'cnipa': '中国国家知识产权局',
    'google_patents': 'Google 专利',
    'arxiv': 'arXiv 学术论文',
  };

  return (
    <div className="space-y-lg">
      {/* 检索条件 */}
      {retrievalKeywords.length > 0 && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm flex items-center gap-2">
            <Search className="w-4 h-4 text-brand-green-dark" />
            检索关键词
          </h4>
          <div className="flex flex-wrap gap-sm">
            {retrievalKeywords.map((kw, i) => (
              <Badge key={i} variant="green-soft">{kw}</Badge>
            ))}
          </div>
        </section>
      )}

      {/* 数据源 */}
      {retrievalDatabases.length > 0 && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm flex items-center gap-2">
            <Shield className="w-4 h-4 text-brand-green-dark" />
            检索数据源
          </h4>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-sm">
            {retrievalDatabases.map((db, i) => (
              <div key={i} className="flex items-center gap-2 p-sm border border-hairline rounded-lg bg-surface-feature">
                <CheckCircle className="w-4 h-4 text-brand-green-dark flex-shrink-0" />
                <span className="text-body-sm text-ink">{dbDisplayName[db] || db}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 检索到的对比文献 */}
      {priorArtReferences.length > 0 && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm flex items-center gap-2">
            <FileText className="w-4 h-4 text-brand-green-dark" />
            对比文献 ({priorArtReferences.length})
          </h4>
          <div className="space-y-sm">
            {priorArtReferences.map((ref, i) => {
              const relevance = ref.riskLevel === 'high' ? 'high' : ref.riskLevel === 'medium' ? 'medium' : 'low';
              const isExpanded = expandedRef === i;
              const relevanceColor = relevance === 'high' ? 'border-orange-200' :
                relevance === 'medium' ? 'border-yellow-200' : 'border-hairline';
              return (
                <div key={i} className={`border rounded-lg overflow-hidden ${relevanceColor}`}>
                  <button
                    className="w-full flex items-center justify-between p-md hover:bg-surface-feature transition-colors text-left"
                    onClick={() => setExpandedRef(isExpanded ? null : i)}
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <span className="text-body-sm-medium text-muted flex-shrink-0">#{i + 1}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-body-sm-medium font-medium text-ink truncate">{ref.title}</p>
                        <div className="flex items-center gap-2 mt-xs">
                          {ref.patentId && <span className="text-caption text-muted">{ref.patentId}</span>}
                          {ref.source && <Badge variant="gray">{ref.source}</Badge>}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                      <Badge variant={relevance === 'high' ? 'orange' : relevance === 'medium' ? 'gray' : 'green'}>
                        {relevance === 'high' ? '高相关' : relevance === 'medium' ? '中相关' : '低相关'}
                      </Badge>
                      {isExpanded ? <ChevronUp className="w-4 h-4 text-muted" /> : <ChevronDown className="w-4 h-4 text-muted" />}
                    </div>
                  </button>
                  {isExpanded && (
                    <div className="border-t border-hairline p-md bg-surface space-y-sm">
                      {/* 检索元信息 */}
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-caption text-muted">
                        {ref.applicant && (
                          <span>申请人：<span className="text-ink">{ref.applicant}</span></span>
                        )}
                        {ref.publicationDate && (
                          <span>公开日：<span className="text-ink">{ref.publicationDate}</span></span>
                        )}
                        {ref.source && (
                          <span>来源：<span className="text-ink">{dbDisplayName[ref.source] || ref.source}</span></span>
                        )}
                      </div>
                      {ref.abstract && (
                        <div>
                          <p className="text-caption font-medium text-muted mb-xs">摘要</p>
                          <p className="text-body-sm text-steel">{ref.abstract}</p>
                        </div>
                      )}
                      {ref.differences.length > 0 && (
                        <div>
                          <p className="text-caption font-medium text-muted mb-xs">与本发明的区别</p>
                          <p className="text-body-sm text-steel">{ref.differences.join('；')}</p>
                        </div>
                      )}
                      {ref.url && (
                        <div className="pt-sm">
                          <a
                            href={ref.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 text-body-sm font-medium text-brand-green-dark hover:underline"
                          >
                            <FileText className="w-3.5 h-3.5" />
                            查看原文
                            <span className="text-xs">↗</span>
                          </a>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* 专利性评分概览 */}
      <section>
        <h4 className="text-body-md-medium font-medium text-ink mb-md">专利性评估</h4>
        <div className="grid grid-cols-3 gap-md">
          {[
            { icon: Zap, name: '新颖性', assessment: novelty },
            { icon: Lightbulb, name: '创造性', assessment: inventiveStep },
            { icon: Shield, name: '实用性', assessment: utility },
          ].map(({ icon: Icon, name, assessment }) => (
            <div key={name} className="border border-hairline rounded-lg p-md text-center">
              <Icon className="w-6 h-6 mx-auto mb-sm text-brand-green-dark" />
              <p className="text-body-sm-medium font-medium text-ink mb-xs">{name}</p>
              <div className="mb-sm">{ratingBadge(assessment.rating)}</div>
              <div className="w-full bg-hairline-soft rounded-full h-2">
                <div
                  className="bg-brand-green h-2 rounded-full transition-all"
                  style={{ width: `${ratingScore(assessment.rating)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
        {overallPatentability && (
          <div className="mt-md p-md bg-surface-feature rounded-lg flex items-center justify-between">
            <span className="text-body-sm-medium font-medium text-ink">综合专利性</span>
            {ratingBadge(overallPatentability)}
          </div>
        )}
      </section>

      {/* 评估理由 */}
      <section>
        <h4 className="text-body-md-medium font-medium text-ink mb-sm">评估分析</h4>
        <div className="space-y-sm">
          {[
            { name: '新颖性分析', rationale: str(novelty.rationale) },
            { name: '创造性分析', rationale: str(inventiveStep.rationale) },
            { name: '实用性分析', rationale: str(utility.rationale) },
          ].filter(item => item.rationale).map(({ name, rationale }) => (
            <div key={name} className="border border-hairline rounded-lg p-md">
              <p className="text-body-sm-medium font-medium text-ink mb-xs">{name}</p>
              <p className="text-body-sm text-steel">{rationale}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 风险因素 */}
      {riskFactors.length > 0 && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-accent-orange" />
            风险因素 ({riskFactors.length})
          </h4>
          <div className="space-y-sm">
            {riskFactors.map((risk, i) => {
              const severity = str(risk.severity);
              const severityColor = severity === 'critical' ? 'bg-red-50 border-red-200' :
                severity === 'high' ? 'bg-orange-50 border-orange-200' :
                'bg-yellow-50 border-yellow-200';
              return (
                <div key={i} className={`border rounded-lg p-md ${severityColor}`}>
                  <div className="flex items-center gap-2 mb-xs">
                    <Badge variant={severity === 'critical' || severity === 'high' ? 'orange' : 'gray'}>
                      {severity === 'critical' ? '严重' : severity === 'high' ? '高' : severity === 'medium' ? '中' : '低'}
                    </Badge>
                    <span className="text-body-sm-medium font-medium text-ink">{str(risk.type)}</span>
                  </div>
                  <p className="text-body-sm text-steel">{str(risk.description)}</p>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* 撰写建议 */}
      {recommendations.length > 0 && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm">撰写建议</h4>
          <ul className="space-y-xs">
            {recommendations.map((r, i) => (
              <li key={i} className="text-body-sm text-steel flex items-start gap-2">
                <Lightbulb className="w-4 h-4 text-brand-green-dark flex-shrink-0 mt-0.5" />
                {r}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* 结论 */}
      {conclusion && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm">结论</h4>
          <p className="text-body-md text-steel bg-surface-feature rounded-lg p-md">{conclusion}</p>
        </section>
      )}
    </div>
  );
}

// ─── 3. 申请文件视图 ────────────────────────────────────────────────────────

interface PatentDraftViewProps {
  data: Record<string, unknown>;
  taskId: string;
  title?: string;
}

export function PatentDraftView({ data, taskId, title }: PatentDraftViewProps) {
  if (!data || Object.keys(data).length === 0) return null;

  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  // 尝试从 data.output 中解析 JSON 结构化数据
  // 后端返回的数据结构是 { agent, output, summary }，其中 output 可能是包含 JSON 的字符串
  let parsedData: Record<string, unknown> = data;
  if (typeof data.output === 'string') {
    // 尝试从 output 字符串中提取 JSON（可能在 ```json ... ``` 代码块中）
    const jsonBlockMatch = data.output.match(/```json\s*([\s\S]*?)\s*```/);
    if (jsonBlockMatch) {
      try {
        parsedData = JSON.parse(jsonBlockMatch[1]);
      } catch {
        // 解析失败，尝试直接匹配 JSON 对象
      }
    }
    if (parsedData === data) {
      // 尝试直接匹配 JSON 对象
      const jsonMatch = data.output.match(/\{[\s\S]*"claims"[\s\S]*\}/);
      if (jsonMatch) {
        try {
          parsedData = JSON.parse(jsonMatch[0]);
        } catch {
          // 解析失败，使用原始 data
        }
      }
    }
  } else if (isRecord(data.output)) {
    // output 已经是对象
    parsedData = data.output as Record<string, unknown>;
  }

  const claims = isRecord(parsedData.claims) ? parsedData.claims : {};
  const description = isRecord(parsedData.description) ? parsedData.description : {};
  const abstract = str(parsedData.abstract);
  const drawings = arr(parsedData.drawings)
    .map((drawing) => normalizePatentDrawing(drawing, taskId))
    .filter((drawing): drawing is PatentDrawing => drawing !== null);

  const independentClaim = str(claims.independent_claim);
  const dependentClaims = arr(claims.dependent_claims).map((c) => str(c)).filter(Boolean);

  const sections = [
    { id: 'claims', name: '权利要求书', icon: FileText, content: [independentClaim, ...dependentClaims].filter(Boolean).join('\n\n') },
    { id: 'tech_field', name: '技术领域', icon: Search, content: str(description.technical_field) },
    { id: 'background', name: '背景技术', icon: FileText, content: str(description.background_art) },
    { id: 'summary', name: '发明内容', icon: Lightbulb, content: str(description.summary_of_invention) },
    { id: 'detailed', name: '具体实施方式', icon: FileText, content: str(description.detailed_description) },
    { id: 'abstract', name: '说明书摘要', icon: FileText, content: abstract },
  ].filter(s => s.content);

  const fullText = sections.map(s => `【${s.name}】\n${s.content}`).join('\n\n');

  return (
    <div className="space-y-lg">
      {/* 文件列表 */}
      <section>
        <div className="flex items-center justify-between mb-md">
          <h4 className="text-body-md-medium font-medium text-ink">生成文件</h4>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              const link = document.createElement('a');
              link.href = workflowApi.exportDocx(taskId);
              link.download = `${title || '专利申请文件'}.docx`;
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
            }}
          >
            <Download className="w-4 h-4 mr-1" />
            下载 DOCX
          </Button>
        </div>

        <div className="space-y-sm">
          {sections.map((section) => {
            const Icon = section.icon;
            const isExpanded = expandedSection === section.id;
            return (
              <div key={section.id} className="border border-hairline rounded-lg overflow-hidden">
                <button
                  className="w-full flex items-center justify-between p-md hover:bg-surface-feature transition-colors"
                  onClick={() => setExpandedSection(isExpanded ? null : section.id)}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-surface-feature flex items-center justify-center">
                      <Icon className="w-4 h-4 text-brand-green-dark" />
                    </div>
                    <div className="text-left">
                      <p className="text-body-sm-medium font-medium text-ink">{section.name}</p>
                      <p className="text-caption text-muted">{section.content.length} 字</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        downloadText(`${taskId}-${section.name}.txt`, section.content);
                      }}
                    >
                      <Download className="w-3 h-3" />
                    </Button>
                    {isExpanded ? <ChevronUp className="w-4 h-4 text-muted" /> : <ChevronDown className="w-4 h-4 text-muted" />}
                  </div>
                </button>
                {isExpanded && (
                  <div className="border-t border-hairline p-md bg-surface">
                    <div className="text-body-sm text-steel whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto">
                      {section.content}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {drawings.length > 0 && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-md">附图</h4>
          <div className="grid gap-md md:grid-cols-2">
            {drawings.map((drawing, index) => {
              const imageUrl = drawing.artifact_url || drawing.artifactUrl || '';
              const figureLabel = drawing.figure_number || `附图 ${index + 1}`;
              const altText = drawingAltText(drawing) || figureLabel;

              return (
                <article key={`${figureLabel}-${index}`} className="border border-hairline rounded-lg overflow-hidden bg-surface">
                  {imageUrl && (
                    <a href={imageUrl} target="_blank" rel="noopener noreferrer" aria-label={`打开${figureLabel}附图`}>
                      <div className="bg-surface-feature border-b border-hairline p-md">
                        <img
                          src={imageUrl}
                          alt={altText}
                          className="w-full max-h-[320px] object-contain rounded-lg bg-surface"
                        />
                      </div>
                    </a>
                  )}
                  <div className="p-md space-y-sm">
                    <div>
                      <p className="text-body-sm-medium font-medium text-ink">{figureLabel}</p>
                      {drawing.title && <p className="text-body-sm text-steel mt-xs">{drawing.title}</p>}
                    </div>
                    {drawing.description && (
                      <p className="text-body-sm text-steel leading-relaxed">{drawing.description}</p>
                    )}
                    {imageUrl && (
                      <a
                        href={imageUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        download
                        className="inline-flex items-center gap-1 text-body-sm-medium font-medium text-brand-green-dark hover:underline"
                      >
                        <Download className="w-3 h-3" />
                        打开 / 下载附图
                      </a>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}

// ─── 4. 审查意见视图 ────────────────────────────────────────────────────────

interface QualityReviewViewProps {
  data: Record<string, unknown>;
  roundIndex?: number;
}

export function QualityReviewView({ data, roundIndex }: QualityReviewViewProps) {
  if (!data || Object.keys(data).length === 0) return null;

  const reviewSummaryData = isRecord(data.review_summary) ? data.review_summary : {};
  const overallScore = normalizeQualityScoreForDisplay(
    num(data.overall_score) ?? num(reviewSummaryData.overall_score)
  );
  const overallRating = str(data.overall_rating || reviewSummaryData.overall_rating);
  const recommendation = str(data.recommendation);
  const reviewSummary = str(data.review_summary) || str(reviewSummaryData.reviewer_notes);
  const revisionSuggestions = arr(data.revision_suggestions).map((s) => str(s)).filter(Boolean);

  const formalCompliance = isRecord(data.formal_compliance) ? data.formal_compliance : {};
  const formalIssues = arr(formalCompliance.issues).filter(isRecord);

  const claimsReview = isRecord(data.claims_review) ? data.claims_review : {};
  const claimsIssues = arr(claimsReview.issues).filter(isRecord);

  const descriptionReview = isRecord(data.description_review) ? data.description_review : {};
  const descriptionIssues = arr(descriptionReview.issues).filter(isRecord);

  const allIssues = [...formalIssues, ...claimsIssues, ...descriptionIssues];

  const recommendationConfig: Record<string, { label: string; color: string }> = {
    approve: { label: '通过', color: 'text-brand-green-dark bg-green-50' },
    revise: { label: '需修改', color: 'text-accent-orange bg-orange-50' },
    reject: { label: '不通过', color: 'text-red-500 bg-red-50' },
  };
  const recConfig = recommendationConfig[recommendation] || { label: recommendation, color: 'text-muted bg-hairline-soft' };

  const scoreColor = (overallScore ?? 0) >= 80 ? 'text-brand-green-dark' :
    (overallScore ?? 0) >= 60 ? 'text-accent-orange' : 'text-red-500';

  return (
    <div className="space-y-lg">
      {roundIndex !== undefined && (
        <div className="flex items-center gap-2 mb-sm">
          <Badge variant="green-soft">第 {roundIndex + 1} 轮审查</Badge>
        </div>
      )}

      {/* 评分概览 */}
      <section className="flex items-center gap-xl p-lg bg-surface-feature rounded-lg">
        {overallScore !== null && (
          <div className="text-center">
            <div className={`text-display-lg font-euclid font-semibold ${scoreColor}`}>
              {overallScore}
            </div>
            <p className="text-caption text-muted">总分</p>
          </div>
        )}
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-sm">
            <span className={`px-3 py-1 rounded-full text-body-sm-medium font-medium ${recConfig.color}`}>
              {recConfig.label}
            </span>
            {overallRating && <Badge variant="gray">{overallRating}</Badge>}
          </div>
          {reviewSummary && (
            <p className="text-body-sm text-steel">{reviewSummary}</p>
          )}
        </div>
      </section>

      {/* 问题列表 */}
      {allIssues.length > 0 && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-md flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-accent-orange" />
            审查问题 ({allIssues.length})
          </h4>
          <div className="space-y-sm">
            {allIssues.map((issue, i) => {
              const severity = str(issue.severity);
              const severityLabel = severity === 'critical' ? '严重' : severity === 'high' ? '高' : severity === 'medium' ? '中' : '低';
              const severityColor = severity === 'critical' ? 'border-red-200 bg-red-50' :
                severity === 'high' ? 'border-orange-200 bg-orange-50' :
                'border-yellow-200 bg-yellow-50';
              return (
                <div key={i} className={`border rounded-lg p-md ${severityColor}`}>
                  <div className="flex items-center justify-between mb-xs">
                    <Badge variant={severity === 'critical' || severity === 'high' ? 'orange' : 'gray'}>
                      {severityLabel}
                    </Badge>
                    <span className="text-caption text-muted">{str(issue.location)}</span>
                  </div>
                  <p className="text-body-sm text-ink mb-xs">{str(issue.description)}</p>
                  {str(issue.suggestion) && (
                    <p className="text-body-sm text-steel">
                      <strong>建议：</strong>{str(issue.suggestion)}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* 修改建议 */}
      {revisionSuggestions.length > 0 && (
        <section>
          <h4 className="text-body-md-medium font-medium text-ink mb-sm flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-brand-green-dark" />
            修改建议
          </h4>
          <ol className="space-y-sm list-decimal list-inside">
            {revisionSuggestions.map((s, i) => (
              <li key={i} className="text-body-sm text-steel">{s}</li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

// ─── 5. 多轮展示容器 ────────────────────────────────────────────────────────

interface MultiRoundViewProps {
  rounds: Record<string, unknown>[];
  renderRound: (data: Record<string, unknown>, index: number) => React.ReactNode;
  label: string;
}

export function MultiRoundView({ rounds, renderRound, label }: MultiRoundViewProps) {
  if (rounds.length <= 1) {
    return <>{rounds[0] ? renderRound(rounds[0], 0) : null}</>;
  }

  return (
    <div className="space-y-xl">
      {rounds.map((round, index) => (
        <div key={index} className="relative">
          {index > 0 && (
            <div className="absolute -top-4 left-0 right-0 border-t border-dashed border-hairline-strong" />
          )}
          <div className="mb-md">
            <Badge variant="green-soft">
              {label} 第 {index + 1} 轮
            </Badge>
          </div>
          {renderRound(round, index)}
        </div>
      ))}
    </div>
  );
}
