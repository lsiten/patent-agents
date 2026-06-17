export interface RetrievalPatentInput {
  patent_id?: unknown;
  reference_id?: unknown;
  patent_number?: unknown;
  publication_number?: unknown;
  document_id?: unknown;
  title?: unknown;
  name?: unknown;
  source?: unknown;
  database?: unknown;
  url?: unknown;
  applicant?: unknown;
  applicants?: unknown;
  assignee?: unknown;
  publication_date?: unknown;
  publicationDate?: unknown;
  similarity_score?: unknown;
  score?: unknown;
  relevance?: unknown;
  risk_level?: unknown;
  key_similarities?: unknown;
  matching_features?: unknown;
  key_features?: unknown;
  key_differences?: unknown;
  differences?: unknown;
  distinguishing_features?: unknown;
  abstract?: unknown;
  summary?: unknown;
  snippet?: unknown;
}

export interface NormalizedRetrievalPatent {
  patentId: string;
  title: string;
  source: string;
  url: string;
  applicant: string;
  publicationDate: string;
  similarityScore: number;
  riskLevel: string;
  similarities: string[];
  differences: string[];
  abstract: string;
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function arr(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function normalizeScore(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0;
  return value > 1 ? value / 100 : value;
}

function normalizeTextList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => str(item)).filter(Boolean);
  }
  const text = str(value);
  return text ? [text] : [];
}

export function buildPatentUrl(patentId: string, source: string): string {
  const id = patentId.trim();
  if (!id) return '';

  const sourceLower = source.toLowerCase();
  if (sourceLower === 'arxiv') {
    return `https://arxiv.org/abs/${encodeURIComponent(id)}`;
  }

  const cleanId = id.replace(/[\s/]/g, '');
  return `https://patents.google.com/patent/${cleanId}`;
}

export function getRetrievalPatentReferences(report: Record<string, unknown>): NormalizedRetrievalPatent[] {
  const candidateFields = [
    report.prior_art_references,
    report.similar_patents,
    report.key_references,
    report.references,
    report.search_results,
    report.patent_results,
    report.retrieved_patents,
    report.citations,
  ];
  if (typeof report.retrieval_results === 'object' && report.retrieval_results !== null) {
    const retrievalResults = report.retrieval_results as Record<string, unknown>;
    candidateFields.push(retrievalResults.references, retrievalResults.results, retrievalResults.patents);
  }
  if (typeof report.results === 'object' && report.results !== null && !Array.isArray(report.results)) {
    const results = report.results as Record<string, unknown>;
    candidateFields.push(results.references, results.patents);
  } else {
    candidateFields.push(report.results);
  }

  const references = candidateFields
    .flatMap((field) => arr(field))
    .filter((item): item is RetrievalPatentInput | string => {
      return typeof item === 'string' || (typeof item === 'object' && item !== null && !Array.isArray(item));
    });

  const seen = new Set<string>();
  return references.map((reference) => {
    const ref = typeof reference === 'string' ? { reference_id: reference } : reference;
    const patentId = (
      str(ref.reference_id) ||
      str(ref.patent_id) ||
      str(ref.patent_number) ||
      str(ref.publication_number) ||
      str(ref.document_id)
    );
    const source = str(ref.source) || str(ref.database);
    const url = str(ref.url) || buildPatentUrl(patentId, source);
    const differences = normalizeTextList(ref.key_differences ?? ref.differences ?? ref.distinguishing_features);
    const similarities = normalizeTextList(ref.key_similarities ?? ref.matching_features ?? ref.key_features);

    return {
      patentId,
      title: str(ref.title) || str(ref.name) || patentId || '未命名对比文献',
      source,
      url,
      applicant: str(ref.applicant) || str(ref.assignee) || normalizeTextList(ref.applicants).join('、'),
      publicationDate: str(ref.publication_date) || str(ref.publicationDate),
      similarityScore: normalizeScore(ref.similarity_score ?? ref.score),
      riskLevel: str(ref.risk_level) || str(ref.relevance) || 'low',
      similarities,
      differences,
      abstract: str(ref.abstract) || str(ref.summary) || str(ref.snippet),
    };
  }).filter((reference) => {
    const key = reference.patentId || `${reference.title}|${reference.source}`;
    if (!key.trim() || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
