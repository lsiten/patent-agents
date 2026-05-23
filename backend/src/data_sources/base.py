from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import asyncio
from datetime import datetime

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..models.domain import PriorArtReference, SearchQuery, DataSourceConfig


class DataSource(ABC):
    """数据源抽象基类"""

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.client: Optional[httpx.AsyncClient] = None
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
            elapsed = asyncio.get_event_loop().time() - self.last_request_time
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self.last_request_time = asyncio.get_event_loop().time()

    @abstractmethod
    async def search(self, query: SearchQuery) -> List[PriorArtReference]:
        """执行检索"""
        pass

    @abstractmethod
    async def get_details(self, reference_id: str) -> Optional[PriorArtReference]:
        """获取详情"""
        pass


# ==================== 专利数据库数据源 ====================

class CNIPASource(DataSource):
    """中国国家知识产权局 (CNIPA) 数据源"""

    def __init__(self, config: Optional[DataSourceConfig] = None):
        default_config = DataSourceConfig(
            source_id="cnipa",
            name="中国国家知识产权局",
            source_type="patent",
            base_url="http://pss-system.cnipa.gov.cn",
            enabled=True,
            rate_limit=30,
        )
        super().__init__(config or default_config)

    async def search(self, query: SearchQuery) -> List[PriorArtReference]:
        """检索中国专利"""
        await self._rate_limit()
        logger.info(f"CNIPA检索: {query.query}")

        # TODO: 实现真实的CNIPA API调用
        # 注意: CNIPA有反爬机制，需要使用浏览器自动化
        # 参考: playwright 实现

        # 模拟返回 - 生产环境替换为真实API调用
        return [
            PriorArtReference(
                reference_id=f"CN{datetime.now().year}1234567A",
                title="模拟专利: 基于AI的智能检索方法",
                abstract="本发明公开了一种基于人工智能的智能专利检索方法...",
                similarity_score=0.75,
                source="cnipa",
            )
        ]

    async def get_details(self, reference_id: str) -> Optional[PriorArtReference]:
        await self._rate_limit()
        return None


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

            if not self.client:
                self.client = httpx.AsyncClient(timeout=30.0)

            response = await self.client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                return self._parse_response(data)
        except Exception as e:
            logger.warning(f"USPTO检索失败: {e}")

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


class EpoSource(DataSource):
    """欧洲专利局 (EPO) 数据源"""

    def __init__(self, config: Optional[DataSourceConfig] = None):
        default_config = DataSourceConfig(
            source_id="epo",
            name="欧洲专利局",
            source_type="patent",
            base_url="https://ops.epo.org",
            enabled=True,
            rate_limit=100,
            auth_required=True,
            credentials_env={"consumer_key": "EPO_CONSUMER_KEY", "consumer_secret": "EPO_CONSUMER_SECRET"},
        )
        super().__init__(config or default_config)

    async def search(self, query: SearchQuery) -> List[PriorArtReference]:
        await self._rate_limit()
        logger.info(f"EPO检索: {query.query}")
        # TODO: 实现EPO OPS API调用
        return []

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
        """使用Playwright浏览器自动化检索Google Patents"""
        await self._rate_limit()
        logger.info(f"Google Patents检索: {query.query}")

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                url = f"{self.config.base_url}/search?q={query.query}&assignee=google"
                await page.goto(url)
                await page.wait_for_selector(".result-item", timeout=10000)

                results = []
                items = await page.query_selector_all(".result-item")
                for item in items[:query.max_results]:
                    try:
                        title_elem = await item.query_selector("h3")
                        number_elem = await item.query_selector(".patent-number")
                        abstract_elem = await item.query_selector(".abstract")

                        title = await title_elem.inner_text() if title_elem else ""
                        pat_num = await number_elem.inner_text() if number_elem else ""
                        abstract = await abstract_elem.inner_text() if abstract_elem else ""

                        if title and pat_num:
                            results.append(PriorArtReference(
                                reference_id=pat_num.strip(),
                                title=title.strip(),
                                abstract=abstract.strip()[:500],
                                similarity_score=0.6,
                                source="google_patents",
                            ))
                    except Exception as e:
                        logger.debug(f"解析专利项失败: {e}")

                await browser.close()
                return results

        except ImportError:
            logger.warning("Playwright未安装，跳过Google Patents检索")
        except Exception as e:
            logger.warning(f"Google Patents检索失败: {e}")

        return []

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

            if not self.client:
                self.client = httpx.AsyncClient(timeout=30.0)

            response = await self.client.get(url, params=params)
            if response.status_code == 200:
                return self._parse_atom_response(response.text)
        except Exception as e:
            logger.warning(f"arXiv检索失败: {e}")

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
            "epo": EpoSource(),
            "cnipa": CNIPASource(),
            "google_patents": GooglePatentsSource(),
            "arxiv": ArxivSource(),
        }
        self.web_fetcher = WebFetchSource()
        logger.info(f"数据源管理器初始化完成，可用数据源: {list(self.sources.keys())}")

    async def search_all(self, query: SearchQuery) -> List[PriorArtReference]:
        """并行检索所有数据源"""
        databases = query.databases or list(self.sources.keys())

        tasks = []
        for source_id in databases:
            source = self.sources.get(source_id)
            if source and source.config.enabled:
                tasks.append(source.search(query))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_references = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"数据源 {databases[i]} 检索失败: {result}")
            else:
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
