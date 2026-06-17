function str(value) {
    return typeof value === 'string' ? value : '';
}
function arr(value) {
    return Array.isArray(value) ? value : [];
}
function normalizeScore(value) {
    if (typeof value !== 'number' || !Number.isFinite(value))
        return 0;
    return value > 1 ? value / 100 : value;
}
function normalizeTextList(value) {
    if (Array.isArray(value)) {
        return value.map((item) => str(item)).filter(Boolean);
    }
    const text = str(value);
    return text ? [text] : [];
}
export function buildPatentUrl(patentId, source) {
    const id = patentId.trim();
    if (!id)
        return '';
    const sourceLower = source.toLowerCase();
    if (sourceLower === 'arxiv') {
        return `https://arxiv.org/abs/${encodeURIComponent(id)}`;
    }
    const cleanId = id.replace(/[\s/]/g, '');
    return `https://patents.google.com/patent/${cleanId}`;
}
export function getRetrievalPatentReferences(report) {
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
        const retrievalResults = report.retrieval_results;
        candidateFields.push(retrievalResults.references, retrievalResults.results, retrievalResults.patents);
    }
    if (typeof report.results === 'object' && report.results !== null && !Array.isArray(report.results)) {
        const results = report.results;
        candidateFields.push(results.references, results.patents);
    }
    else {
        candidateFields.push(report.results);
    }
    const references = candidateFields
        .flatMap((field) => arr(field))
        .filter((item) => {
        return typeof item === 'string' || (typeof item === 'object' && item !== null && !Array.isArray(item));
    });
    const seen = new Set();
    return references.map((reference) => {
        const ref = typeof reference === 'string' ? { reference_id: reference } : reference;
        const patentId = (str(ref.reference_id) ||
            str(ref.patent_id) ||
            str(ref.patent_number) ||
            str(ref.publication_number) ||
            str(ref.document_id));
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
        if (!key.trim() || seen.has(key))
            return false;
        seen.add(key);
        return true;
    });
}
