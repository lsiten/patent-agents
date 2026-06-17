from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import asyncio
from datetime import datetime
import re
from urllib.parse import quote

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.core.config import settings
from ..models.domain import PriorArtReference, SearchQuery, DataSourceConfig


class DataSource(ABC):
    """数据源抽象基类"""

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.client: Optional[httpx.AsyncClient] = None
        self.last_error: Optional[str] = None
        self.last_request_time: float = 0
        self.min_interval = 60.0 / config.rate_limit if config.rate_limit > 0 else 0

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def _rate_limit(self):
        """简单速率限制"""
        if self.min_interval > 0:
            elapsed = asyncio.get_running_loop().time() - self.last_request_time
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self.last_request_time = asyncio.get_running_loop().time()

    @abstractmethod
    async def search(self, query: SearchQuery) -> List[PriorArtReference]:
        """执行检索"""
        pass

    @abstractmethod
    async def get_details(self, reference_id: str) -> Optional[PriorArtReference]:
        """获取详情"""
        pass


# ==================== 专利数据库数据源 ====================

class UsptoSource(DataSource):
    """美国专利商标局 (USPTO) 数据源"""

    def __init__(self, config: Optional[DataSourceConfig] = None):
        default_config = DataSourceConfig(
            source_id="uspto",
            name="美国专利商标局",
            source_type="patent",
            base_url="https://developer.uspto.gov",
            enabled=True,
            rate_limit=60,
        )
        super().__init__(config or default_config)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def search(self, query: SearchQuery) -> List[PriorArtReference]:
        """USPTO专利检索"""
        await self._rate_limit()
        logger.info(f"USPTO检索: {query.query}")

        try:
            # USPTO公开API
            url = f"{self.config.base_url}/api/patents/v1/claims/search"
            params = {
                "query": query.query,
                "rows": min(query.max_results, 50),
            }

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                self.last_error = None
                return self._parse_response(data)
            self.last_error = f"USPTO HTTP status={response.status_code}"
        except Exception as e:
            self.last_error = f"USPTO检索失败: {e}"
            logger.warning(self.last_error)

        return []

    def _parse_response(self, data: Dict[str, Any]) -> List[PriorArtReference]:
        """解析USPTO响应"""
        results = []
        for item in data.get("results", []):
            try:
                ref = PriorArtReference(
                    reference_id=item.get("patentNumber", ""),
                    title=item.get("inventionTitle", ""),
                    publication_date=item.get("publicationDate"),
                    abstract=item.get("claimText", "")[:500],
                    similarity_score=0.5,  # 需要额外计算相似度
                    source="uspto",
                    url=f"https://patft.uspto.gov/netacgi/nph-Parser?patentnumber={item.get('patentNumber')}"
                )
                results.append(ref)
            except Exception as e:
                logger.debug(f"解析USPTO专利失败: {e}")
        return results

    async def get_details(self, reference_id: str) -> Optional[PriorArtReference]:
        await self._rate_limit()
        return None


class GooglePatentsSource(DataSource):
    """Google Patents 数据源 - 浏览器自动化"""

    def __init__(self, config: Optional[DataSourceConfig] = None):
        default_config = DataSourceConfig(
            source_id="google_patents",
            name="Google Patents",
            source_type="patent",
            base_url="https://patents.google.com",
            enabled=True,
            rate_limit=10,
        )
        super().__init__(config or default_config)

    async def search(self, query: SearchQuery) -> List[PriorArtReference]:
        """检索 Google Patents，并返回页面中可核验的公开专利记录。"""
        await self._rate_limit()
        logger.info(f"Google Patents检索: {query.query}")

        encoded_query = quote(f"q={query.query}", safe="")
        url = f"{self.config.base_url}/xhr/query?url={encoded_query}&exp="
        http_results = await self._search_with_http(url, query.max_results)
        if http_results:
            return http_results

        logger.warning("Google Patents真实HTTP检索未返回可核验证据")
        return []

    async def _search_with_http(self, url: str, max_results: int) -> List[PriorArtReference]:
        try:
            async with httpx.AsyncClient(
                    timeout=30.0,
                    follow_redirects=True,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
                        )
                    },
                ) as client:
                response = await client.get(url)
            if response.status_code != 200:
                self.last_error = f"Google Patents HTTP status={response.status_code}"
                logger.warning(f"Google Patents HTTP检索失败: status={response.status_code}")
                return []
            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                parsed = self._parse_xhr_response(response.json(), max_results)
                self.last_error = None if parsed else "Google Patents JSON响应无可核验专利记录"
                return parsed
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(response.text, "html.parser")
            candidates = soup.select("search-result-item, article, .result, .result-item")
            if not candidates:
                candidates = [
                    link.parent
                    for link in soup.select('a[href*="/patent/"]')
                    if link.parent is not None
                ]
            results: List[PriorArtReference] = []
            seen = set()
            for candidate in candidates:
                text = candidate.get_text("\n", strip=True)
                href = ""
                link = candidate.select_one('a[href*="/patent/"]')
                if link:
                    href = str(link.get("href") or "")
                parsed = self._parse_result_text(text, href=href)
                if not parsed or parsed["reference_id"] in seen:
                    continue
                seen.add(parsed["reference_id"])
                results.append(PriorArtReference(
                    reference_id=parsed["reference_id"],
                    title=parsed["title"],
                    abstract=parsed.get("abstract", "")[:500],
                    publication_date=parsed.get("publication_date"),
                    similarity_score=0.6,
                    source="google_patents",
                    url=f"{self.config.base_url}/patent/{parsed['reference_id']}",
                ))
                if len(results) >= max_results:
                    break
            self.last_error = None if results else "Google Patents HTML响应无可核验专利记录"
            return results
        except Exception as e:
            self.last_error = f"Google Patents HTTP检索失败: {e}"
            logger.warning(self.last_error)
            return []

    def _parse_xhr_response(self, data: Dict[str, Any], max_results: int) -> List[PriorArtReference]:
        results: List[PriorArtReference] = []
        seen = set()
        clusters = ((data.get("results") or {}).get("cluster") or [])
        for cluster in clusters:
            for item in cluster.get("result") or []:
                patent = item.get("patent") or {}
                publication_number = str(patent.get("publication_number") or "").strip()
                if not publication_number or publication_number in seen:
                    continue
                seen.add(publication_number)
                title = str(patent.get("title") or publication_number).strip()
                snippet = re.sub(r"<[^>]+>", "", str(patent.get("snippet") or "")).strip()
                results.append(PriorArtReference(
                    reference_id=publication_number,
                    title=title,
                    applicant=patent.get("assignee"),
                    publication_date=patent.get("publication_date"),
                    abstract=snippet[:500],
                    similarity_score=max(0.1, 0.75 - (0.03 * len(results))),
                    source="google_patents",
                    url=f"{self.config.base_url}/patent/{publication_number}",
                ))
                if len(results) >= max_results:
                    return results
        return results

    def _parse_result_text(self, text: str, href: str = "") -> Optional[Dict[str, Any]]:
        normalized = re.sub(r"\s+", " ", text or "").strip()
        ref_match = re.search(
            r"\b(CN|US|EP|WO|JP|KR)\s?[\d/]{4,}[A-Z]?\d?\b",
            f"{href} {normalized}",
            re.IGNORECASE,
        )
        if not ref_match:
            return None
        reference_id = re.sub(r"\s+", "", ref_match.group(0)).upper()
        title = normalized
        if reference_id in title:
            title = title.split(reference_id, 1)[-1].strip(" -:：")
        title = title[:160] or reference_id
        date_match = re.search(r"\b(19|20)\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}", normalized)
        publication_date = date_match.group(0) if date_match else None
        abstract = normalized[:500]
        return {
            "reference_id": reference_id,
            "title": title,
            "publication_date": publication_date,
            "abstract": abstract,
        }

    async def get_details(self, reference_id: str) -> Optional[PriorArtReference]:
        await self._rate_limit()
        return None


# ==================== 学术论文数据源 ====================

class ArxivSource(DataSource):
    """arXiv 预印本数据源"""

    def __init__(self, config: Optional[DataSourceConfig] = None):
        default_config = DataSourceConfig(
            source_id="arxiv",
            name="arXiv",
            source_type="academic",
            base_url="http://export.arxiv.org",
            enabled=True,
            rate_limit=20,
        )
        super().__init__(config or default_config)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def search(self, query: SearchQuery) -> List[PriorArtReference]:
        await self._rate_limit()
        logger.info(f"arXiv检索: {query.query}")

        try:
            url = f"{self.config.base_url}/api/query"
            params = {
                "search_query": f"all:{query.query}",
                "start": 0,
                "max_results": min(query.max_results, 20),
            }

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, params=params)
            if response.status_code == 200:
                self.last_error = None
                return self._parse_atom_response(response.text)
            self.last_error = f"arXiv HTTP status={response.status_code}"
        except Exception as e:
            self.last_error = f"arXiv检索失败: {e}"
            logger.warning(self.last_error)

        return []

    def _parse_atom_response(self, xml_content: str) -> List[PriorArtReference]:
        """解析Atom XML响应"""
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            results = []
            for entry in root.findall("atom:entry", ns):
                try:
                    title = entry.find("atom:title", ns)
                    summary = entry.find("atom:summary", ns)
                    id_elem = entry.find("atom:id", ns)

                    results.append(PriorArtReference(
                        reference_id=id_elem.text.split("/")[-1] if id_elem is not None else "",
                        title=title.text if title is not None else "",
                        abstract=summary.text[:500] if summary is not None else "",
                        similarity_score=0.5,
                        source="arxiv",
                        url=id_elem.text if id_elem is not None else None,
                    ))
                except Exception as e:
                    logger.debug(f"解析arXiv条目失败: {e}")
            return results
        except Exception as e:
            logger.warning(f"解析arXiv响应失败: {e}")
            return []

    async def get_details(self, reference_id: str) -> Optional[PriorArtReference]:
        await self._rate_limit()
        return None


# ==================== 通用网页抓取 ====================

class WebFetchSource:
    """通用网页内容抓取 - 作为参考资料"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None

    async def fetch(self, url: str) -> Optional[Dict[str, Any]]:
        """抓取网页内容"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(response.text, 'html.parser')

                    # 提取主要内容
                    title = soup.title.string if soup.title else ""

                    # 尝试提取正文
                    body = ""
                    for selector in ['article', 'main', '.content', '#content', 'body']:
                        elem = soup.select_one(selector)
                        if elem:
                            body = elem.get_text(separator='\n', strip=True)
                            if len(body) > 500:
                                break

                    return {
                        "url": url,
                        "title": title,
                        "content": body[:5000],  # 限制长度
                        "status": response.status_code,
                    }
        except Exception as e:
            logger.warning(f"网页抓取失败 {url}: {e}")
        return None

    async def fetch_with_browser(self, url: str) -> Optional[Dict[str, Any]]:
        """使用Playwright浏览器抓取 - 支持JS渲染页面"""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle")

                title = await page.title()
                content = await page.inner_text("body")

                await browser.close()

                return {
                    "url": url,
                    "title": title,
                    "content": content[:5000],
                    "method": "browser",
                }
        except ImportError:
            logger.warning("Playwright未安装，无法使用浏览器抓取")
        except Exception as e:
            logger.warning(f"浏览器抓取失败 {url}: {e}")
        return None


# ==================== 数据源管理器 ====================

class DataSourceManager:
    """数据源管理器 - 统一调度所有数据源"""

    def __init__(self):
        self.sources: Dict[str, DataSource] = {
            "uspto": UsptoSource(),
        }
        if settings.patent_db.enable_google_patents:
            self.sources["google_patents"] = GooglePatentsSource()
        if settings.patent_db.enable_arxiv:
            self.sources["arxiv"] = ArxivSource()
        self.web_fetcher = WebFetchSource()
        self.last_search_status: Dict[str, Dict[str, Any]] = {}
        logger.info(f"数据源管理器初始化完成，可用数据源: {list(self.sources.keys())}")

    async def search_all(self, query: SearchQuery) -> List[PriorArtReference]:
        """并行检索所有数据源"""
        databases = query.databases or list(self.sources.keys())

        tasks = []
        task_sources: List[str] = []
        self.last_search_status = {}
        for source_id in databases:
            source = self.sources.get(source_id)
            if source and source.config.enabled:
                source.last_error = None
                tasks.append(source.search(query))
                task_sources.append(source_id)
            else:
                self.last_search_status[source_id] = {
                    "success": False,
                    "count": 0,
                    "error": "数据源未配置或未启用",
                }

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_references = []

        for i, result in enumerate(results):
            source_id = task_sources[i]
            if isinstance(result, Exception):
                self.last_search_status[source_id] = {
                    "success": False,
                    "count": 0,
                    "error": str(result),
                }
                logger.warning(f"数据源 {source_id} 检索失败: {result}")
            else:
                source = self.sources.get(source_id)
                self.last_search_status[source_id] = {
                    "success": bool(result),
                    "count": len(result),
                    "error": source.last_error if source and not result else None,
                }
                all_references.extend(result)

        # 去重（根据reference_id）
        seen = set()
        unique_references = []
        for ref in all_references:
            if ref.reference_id and ref.reference_id not in seen:
                seen.add(ref.reference_id)
                unique_references.append(ref)

        logger.info(f"多数据源检索完成，共找到 {len(unique_references)} 篇参考文献")
        return unique_references

    async def fetch_web_references(self, urls: List[str]) -> List[Dict[str, Any]]:
        """抓取网页参考资料"""
        tasks = [self.web_fetcher.fetch(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if not isinstance(r, Exception) and r is not None]


# 全局数据源管理器实例
_dsm_instance: Optional[DataSourceManager] = None


def get_data_source_manager() -> DataSourceManager:
    """获取全局数据源管理器实例"""
    global _dsm_instance
    if _dsm_instance is None:
        _dsm_instance = DataSourceManager()
    return _dsm_instance
