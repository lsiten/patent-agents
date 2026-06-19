import time

from fastapi import APIRouter

from src.api.schemas import (
    KnowledgeBaseSearchResponse,
    PriorArtReferenceResponse,
    SearchPatentRequest,
    SearchResponse,
)
from src.data_sources.base import get_data_source_manager
from src.knowledge.base import get_knowledge_base

router = APIRouter(tags=["search"])


@router.post("/search/patents", response_model=SearchResponse)
async def search_patents(request: SearchPatentRequest):
    """搜索现有技术专利。"""
    start_time = time.time()

    data_source_manager = get_data_source_manager()
    results = await data_source_manager.search_all(request)

    response_results = [
        PriorArtReferenceResponse(
            reference_id=r.reference_id,
            title=r.title,
            publication_date=r.publication_date,
            applicant=r.applicant,
            abstract=r.abstract,
            similarity_score=r.similarity_score,
            source=r.source,
            url=r.url,
        )
        for r in results
    ]

    return SearchResponse(
        total=len(results),
        results=response_results,
        query=request.query,
        search_time=time.time() - start_time,
    )


@router.get("/knowledge/search", response_model=KnowledgeBaseSearchResponse)
async def search_knowledge_base(query: str, top_k: int = 5):
    """搜索本地知识库中的专利。"""
    kb = get_knowledge_base()
    patents = kb.search_similar(query, top_k)

    return KnowledgeBaseSearchResponse(
        total=len(patents),
        patents=patents,
        query=query,
    )
