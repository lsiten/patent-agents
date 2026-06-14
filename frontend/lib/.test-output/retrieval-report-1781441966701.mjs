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
    if (sourceLower === 'cnipa' || sourceLower === '中国国家知识产权局') {
        return `https://pss-system.cponline.cnipa.gov.cn/conventionalSearch?searchWord=${encodeURIComponent(id)}`;
    }
    if (sourceLower === 'epo' || sourceLower === '欧洲专利局' || id.startsWith('EP')) {
        return `https://worldwide.espacenet.com/patent/search?q=${encodeURIComponent(id)}`;
    }
    if (sourceLower === 'wipo' || id.startsWith('WO')) {
        return `https://patentscope.wipo.int/search/en/detail.jsf?docId=${encodeURIComponent(id)}`;
    }
    if (sourceLower === 'arxiv') {
        return `https://arxiv.org/abs/${encodeURIComponent(id)}`;
    }
    const cleanId = id.replace(/[\s/]/g, '');
    return `https://patents.google.com/patent/${cleanId}`;
}
export function getRetrievalPatentReferences(report) {
    const priorArtReferences = arr(report.prior_art_references).filter((item) => {
        return typeof item === 'object' && item !== null && !Array.isArray(item);
    });
    const similarPatents = arr(report.similar_patents).filter((item) => {
        return typeof item === 'object' && item !== null && !Array.isArray(item);
    });
    const references = priorArtReferences.length > 0 ? priorArtReferences : similarPatents;
    return references.map((reference) => {
        const patentId = str(reference.reference_id) || str(reference.patent_id);
        const source = str(reference.source);
        const url = str(reference.url) || buildPatentUrl(patentId, source);
        const differences = normalizeTextList(reference.key_differences ?? reference.differences);
        const similarities = normalizeTextList(reference.key_similarities ?? reference.matching_features);
        return {
            patentId,
            title: str(reference.title),
            source,
            url,
            applicant: str(reference.applicant),
            publicationDate: str(reference.publication_date),
            similarityScore: normalizeScore(reference.similarity_score),
            riskLevel: str(reference.risk_level) || 'low',
            similarities,
            differences,
            abstract: str(reference.abstract),
        };
    });
}
