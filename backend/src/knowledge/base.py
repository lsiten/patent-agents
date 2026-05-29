from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from pathlib import Path
import json
import hashlib

from loguru import logger

from ..models.domain import FinalizedPatent, KeyFeature, Claim, DescriptionSection
from ..document_gen.docx_parser import (
    FinalizedPatentEntry,
    ParsedPatentDocx,
    scan_finalized_patents_dir,
)


class KnowledgeBase(ABC):
    """知识库抽象基类"""

    @abstractmethod
    def add_patent(self, patent: FinalizedPatent) -> str:
        """添加定稿专利到知识库"""
        pass

    @abstractmethod
    def search_similar(self, tech_description: str, top_k: int = 5) -> List[FinalizedPatent]:
        """搜索相似专利作为参考"""
        pass

    @abstractmethod
    def get_patent_by_id(self, patent_id: str) -> Optional[FinalizedPatent]:
        """根据ID获取专利"""
        pass

    @abstractmethod
    def get_exemplars(self, tech_field: Optional[str] = None) -> List[FinalizedPatent]:
        """获取范例专利"""
        pass


class LocalFileKnowledgeBase(KnowledgeBase):
    """本地文件知识库 - 存储在 ./finalized_patents 目录下"""

    def __init__(self, base_dir: str = "./finalized_patents"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.base_dir / "index.json"
        self._load_index()
        logger.info(f"本地知识库初始化完成，路径: {self.base_dir}，专利数量: {len(self.index)}")

    def _load_index(self):
        """加载索引"""
        if self.index_file.exists():
            with open(self.index_file, 'r', encoding='utf-8') as f:
                self.index = json.load(f)
        else:
            self.index = {}

    def _save_index(self):
        """保存索引"""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)

    def _generate_id(self, title: str, tech_field: str) -> str:
        """生成专利ID"""
        content = f"{title}:{tech_field}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def _get_patent_path(self, patent_id: str) -> Path:
        """获取专利文件路径"""
        return self.base_dir / f"{patent_id}.json"

    def add_patent(self, patent: FinalizedPatent) -> str:
        """添加定稿专利到知识库"""
        if not patent.patent_id:
            patent.patent_id = self._generate_id(patent.title, patent.tech_field)

        # 提取风格特征
        patent.style_features = self._extract_style_features(patent)

        # 保存文件
        patent_path = self._get_patent_path(patent.patent_id)
        with open(patent_path, 'w', encoding='utf-8') as f:
            json.dump(patent.dict(), f, ensure_ascii=False, indent=2, default=str)

        # 更新索引
        self.index[patent.patent_id] = {
            "title": patent.title,
            "tech_field": patent.tech_field,
            "ipc_classification": patent.ipc_classification,
            "is_exemplar": patent.is_exemplar,
            "quality_score": patent.quality_score,
            "tags": patent.tags,
        }
        self._save_index()

        logger.info(f"专利已添加到知识库: {patent.title} (ID: {patent.patent_id})")
        return patent.patent_id

    def _extract_style_features(self, patent: FinalizedPatent) -> Dict[str, Any]:
        """提取专利的写作风格特征"""
        features = {}

        # 权利要求特征
        if patent.claims:
            features["claim_count"] = len(patent.claims)
            features["independent_claim_count"] = sum(
                1 for c in patent.claims if c.claim_type == "independent"
            )
            avg_claim_length = sum(len(c.content) for c in patent.claims) / len(patent.claims)
            features["avg_claim_length"] = round(avg_claim_length, 2)

        # 说明书特征
        if patent.description_sections:
            total_words = sum(s.word_count for s in patent.description_sections)
            features["total_description_words"] = total_words

            section_dist = {}
            for section in patent.description_sections:
                section_dist[section.section_name] = section.word_count
            features["section_word_distribution"] = section_dist

        # 术语特征
        features["standard_terms"] = patent.standard_terms

        return features

    def search_similar(self, tech_description: str, top_k: int = 5) -> List[FinalizedPatent]:
        """
        搜索相似专利 - 基于关键词匹配
        生产环境建议接入向量数据库: Pinecone / Chroma / Milvus
        """
        keywords = self._extract_keywords(tech_description)
        logger.info(f"搜索相似专利，关键词: {keywords}")

        results = []
        for patent_id, meta in self.index.items():
            score = self._calculate_similarity(keywords, meta)
            if score > 0:
                patent = self.get_patent_by_id(patent_id)
                if patent:
                    results.append((score, patent))

        results.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in results[:top_k]]

    def _extract_keywords(self, text: str) -> List[str]:
        """简单关键词提取"""
        stop_words = {"的", "是", "在", "和", "与", "或", "一种", "该", "其", "用于"}
        words = text.replace(",", " ").replace(".", " ").split()
        return [w for w in words if w not in stop_words and len(w) > 1]

    def _calculate_similarity(self, keywords: List[str], meta: Dict) -> float:
        """计算相似度得分"""
        text = f"{meta['title']} {meta['tech_field']} {' '.join(meta.get('tags', []))}"
        text_lower = text.lower()
        matched = sum(1 for kw in keywords if kw.lower() in text_lower)
        return matched / len(keywords) if keywords else 0

    def get_patent_by_id(self, patent_id: str) -> Optional[FinalizedPatent]:
        """根据ID获取专利"""
        patent_path = self._get_patent_path(patent_id)
        if not patent_path.exists():
            return None

        with open(patent_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return FinalizedPatent(**data)

    def get_exemplars(self, tech_field: Optional[str] = None) -> List[FinalizedPatent]:
        """获取范例专利"""
        exemplar_ids = [
            pid for pid, meta in self.index.items()
            if meta.get("is_exemplar", False)
        ]

        if tech_field:
            # 过滤技术领域
            exemplar_ids = [
                pid for pid in exemplar_ids
                if tech_field.lower() in self.index[pid]["tech_field"].lower()
            ]

        patents = []
        for pid in exemplar_ids:
            patent = self.get_patent_by_id(pid)
            if patent:
                patents.append(patent)
        return patents

    def list_all_patents(self) -> List[Dict]:
        """列出所有专利元数据"""
        return list(self.index.values())

    def import_from_docx_dir(self, docx_dir: Path) -> int:
        """
        从定稿文件目录导入专利到知识库。

        解析每个子目录中的 B-*.docx（定稿专利）为 FinalizedPatent，
        同时将 A-*.docx（交底书/对话记录）的文本作为 writing_patterns 补充。

        Args:
            docx_dir: 定稿文件根目录路径

        Returns:
            成功导入的专利数量
        """
        entries = scan_finalized_patents_dir(docx_dir)
        imported = 0

        for entry in entries:
            if not entry.patent_doc:
                logger.warning(f"跳过无 B 文件的专利: {entry.directory_name}")
                continue

            try:
                patent = self._convert_to_finalized_patent(entry)
                self.add_patent(patent)
                imported += 1
            except Exception as e:
                logger.error(f"导入专利失败 {entry.directory_name}: {e}")

        logger.info(f"从 docx 目录导入 {imported}/{len(entries)} 篇定稿专利")
        return imported

    def _convert_to_finalized_patent(self, entry: FinalizedPatentEntry) -> FinalizedPatent:
        """将解析后的 docx 数据转换为 FinalizedPatent 模型。"""
        parsed = entry.patent_doc
        assert parsed is not None

        # Convert claims
        claims = []
        for i, claim_text in enumerate(parsed.claims, 1):
            # Detect if it's independent or dependent
            is_dependent = "根据权利要求" in claim_text
            claims.append(Claim(
                claim_number=i,
                claim_type="dependent" if is_dependent else "independent",
                content=claim_text,
                dependencies=[],
                category="method" if "方法" in parsed.title else "system",
            ))

        # Convert description sections
        desc_sections = []
        for name, section in parsed.description_sections.items():
            desc_sections.append(DescriptionSection(
                section_name=name,
                content=section.content,
                word_count=len(section.content),
            ))

        # Extract writing patterns from A-file (disclosure)
        writing_patterns = []
        if entry.disclosure_doc and entry.disclosure_doc.full_text:
            # Store a summary of the disclosure style
            writing_patterns.append(f"交底书内容摘要（前2000字）: {entry.disclosure_doc.full_text[:2000]}")

        # Build standard terms from the patent text
        standard_terms = self._extract_standard_terms(parsed)

        patent = FinalizedPatent(
            patent_id=self._generate_id(parsed.title, parsed.ipc_code or "unknown"),
            title=parsed.title,
            patent_number=None,
            tech_field=self._infer_tech_field(parsed),
            ipc_classification=[parsed.ipc_code] if parsed.ipc_code else [],
            claims=claims,
            description_sections=desc_sections,
            abstract=parsed.abstract,
            style_features={},
            writing_patterns=writing_patterns,
            standard_terms=standard_terms,
            quality_score=0.9,  # 定稿专利默认高质量
            is_exemplar=True,  # 定稿专利作为范例
            source="docx_import",
            tags=[parsed.ipc_code] if parsed.ipc_code else [],
        )

        return patent

    def _infer_tech_field(self, parsed: ParsedPatentDocx) -> str:
        """从说明书技术领域部分推断技术领域。"""
        tech_section = parsed.description_sections.get("技术领域")
        if tech_section and tech_section.content:
            return tech_section.content[:100]
        return parsed.title

    def _extract_standard_terms(self, parsed: ParsedPatentDocx) -> List[str]:
        """从定稿专利中提取标准术语。"""
        terms = set()
        # Extract key terms from claims (quoted terms, defined terms)
        for claim in parsed.claims:
            # Find terms in 「」 or "" or specific patterns
            import re
            # Match "所述XXX" patterns
            matches = re.findall(r"所述([\u4e00-\u9fff]+)", claim)
            for m in matches:
                if 2 <= len(m) <= 8:
                    terms.add(m)
        return list(terms)[:30]  # Limit to 30 terms

    def get_docx_content_for_llm(
        self, tech_field: Optional[str] = None, max_patents: int = 2
    ) -> str:
        """
        获取定稿专利的文本内容，用于注入 LLM prompt 作为写作风格参考。

        返回格式化的参考文本，包含权利要求书和说明书片段。
        """
        exemplars = self.get_exemplars(tech_field)
        if not exemplars:
            exemplars = list(self.get_patent_by_id(pid) for pid in list(self.index.keys())[:max_patents])
            exemplars = [p for p in exemplars if p is not None]

        if not exemplars:
            return ""

        reference_parts = []
        for patent in exemplars[:max_patents]:
            parts = [f"【参考专利：{patent.title}】"]

            # Add claims excerpt
            if patent.claims:
                claims_text = "\n".join(c.content for c in patent.claims[:3])
                parts.append(f"[权利要求书片段]\n{claims_text[:1500]}")

            # Add description excerpt
            for section in patent.description_sections:
                if section.section_name in ("技术领域", "背景技术", "发明内容"):
                    parts.append(f"[{section.section_name}]\n{section.content[:800]}")

            # Add disclosure content if available
            if patent.writing_patterns:
                for pattern in patent.writing_patterns:
                    if pattern.startswith("交底书内容摘要"):
                        parts.append(f"[交底书参考]\n{pattern[10:800]}")
                        break

            reference_parts.append("\n".join(parts))

        return "\n\n---\n\n".join(reference_parts)


# 全局知识库实例
_kb_instance: Optional[LocalFileKnowledgeBase] = None


def get_knowledge_base() -> LocalFileKnowledgeBase:
    """获取全局知识库实例"""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = LocalFileKnowledgeBase()
    return _kb_instance
