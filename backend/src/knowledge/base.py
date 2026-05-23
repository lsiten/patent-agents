from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from pathlib import Path
import json
import hashlib

from loguru import logger

from ..models.domain import FinalizedPatent, KeyFeature


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


# 全局知识库实例
_kb_instance: Optional[LocalFileKnowledgeBase] = None


def get_knowledge_base() -> LocalFileKnowledgeBase:
    """获取全局知识库实例"""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = LocalFileKnowledgeBase()
    return _kb_instance
