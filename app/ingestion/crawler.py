"""Extração (E do ETL): crawlers assíncronos das duas fontes oficiais.

* HelpCenterCrawler -> Product Fruits (/pt). Tenta sitemap.xml; se não houver,
  faz BFS a partir da home seguindo apenas links internos sob /pt.
* ApiDocCrawler -> Apidog (SSR). A sidebar presente em qualquer página já lista
  todos os artigos; ainda assim fazemos BFS raso para capturar páginas novas
  (descoberta automática — RF01).

Politeness: concorrência limitada por semáforo + delay configurável + UA própria.
"""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from app.config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class RawPage:
    url: str
    html: str
    source: str  # "helpcenter" | "apidoc"
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _normalize(url: str) -> str:
    url, _ = urldefrag(url)
    return url.rstrip("/")


class _BaseCrawler:
    source = "generic"

    def __init__(self, base_url: str, settings: Settings):
        self.base_url = _normalize(base_url)
        self.host = urlparse(self.base_url).netloc
        self.s = settings
        self._sem = asyncio.Semaphore(settings.crawl_concurrency)
        self._seen: set[str] = set()

    # ----------------------------------------------------------------- http
    async def _fetch(self, client: httpx.AsyncClient, url: str) -> str | None:
        async with self._sem:
            try:
                r = await client.get(url)
                await asyncio.sleep(self.s.crawl_delay_seconds)
            except httpx.HTTPError as exc:
                logger.warning("Falha ao buscar %s: %s", url, exc)
                return None
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", "html"):
            logger.warning("Ignorando %s (status=%s)", url, r.status_code)
            return None
        return r.text

    def _extract_links(self, html: str, page_url: str) -> set[str]:
        links = set()
        for href in re.findall(r'href=["\']([^"\'#]+)', html):
            url = _normalize(urljoin(page_url, href.strip()))
            if urlparse(url).netloc == self.host and self._allowed(url):
                links.add(url)
        return links

    # --------------------------------------------------------- customização
    def _allowed(self, url: str) -> bool:  # links que podem ser SEGUIDOS
        return True

    def _is_content(self, url: str) -> bool:  # páginas que devem ser INDEXADAS
        return True

    # ------------------------------------------------------------------ bfs
    async def crawl(self) -> list[RawPage]:
        pages: list[RawPage] = []
        headers = {"User-Agent": self.s.user_agent, "Accept-Language": "pt-BR,pt;q=0.9"}
        async with httpx.AsyncClient(
            headers=headers, timeout=self.s.request_timeout_seconds, follow_redirects=True
        ) as client:
            queue: list[str] = await self._seed(client)
            while queue and len(self._seen) < self.s.crawl_max_pages:
                batch, queue = queue[: self.s.crawl_concurrency * 2], queue[self.s.crawl_concurrency * 2:]
                batch = [u for u in batch if u not in self._seen]
                for u in batch:
                    self._seen.add(u)
                htmls = await asyncio.gather(*(self._fetch(client, u) for u in batch))
                for url, html in zip(batch, htmls):
                    if not html:
                        continue
                    if self._is_content(url):
                        pages.append(RawPage(url=url, html=html, source=self.source))
                    for link in self._extract_links(html, url):
                        if link not in self._seen and link not in queue:
                            queue.append(link)
        logger.info("[%s] %d páginas de conteúdo coletadas (%d URLs visitadas)",
                    self.source, len(pages), len(self._seen))
        return pages

    async def _seed(self, client: httpx.AsyncClient) -> list[str]:
        sitemap_urls = await self._try_sitemap(client)
        return sitemap_urls or [self.base_url]

    async def _try_sitemap(self, client: httpx.AsyncClient) -> list[str]:
        root = f"{urlparse(self.base_url).scheme}://{self.host}"
        try:
            r = await client.get(f"{root}/sitemap.xml")
        except httpx.HTTPError:
            return []
        if r.status_code != 200 or "<urlset" not in r.text[:2000].lower():
            return []
        try:
            tree = ET.fromstring(r.text)
        except ET.ParseError:
            return []
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [
            _normalize(loc.text.strip())
            for loc in tree.findall(".//sm:loc", ns)
            if loc.text and self._allowed(_normalize(loc.text.strip()))
        ]
        if urls:
            logger.info("[%s] sitemap.xml com %d URLs", self.source, len(urls))
        return urls


class HelpCenterCrawler(_BaseCrawler):
    """Help Center Product Fruits — segue apenas o espaço /pt."""

    source = "helpcenter"

    def _allowed(self, url: str) -> bool:
        path = urlparse(url).path
        return path == "/pt" or path.startswith("/pt/")

    def _is_content(self, url: str) -> bool:
        return "/pt/article/" in urlparse(url).path


class ApiDocCrawler(_BaseCrawler):
    """Apidog — todas as páginas de slug na raiz são conteúdo."""

    source = "apidoc"
    _SKIP = re.compile(r"\.(png|jpe?g|gif|css|js|ico|svg|pdf)$", re.I)

    def _allowed(self, url: str) -> bool:
        return not self._SKIP.search(urlparse(url).path)

    def _is_content(self, url: str) -> bool:
        return self._allowed(url)


async def crawl_all_sources(settings: Settings) -> list[RawPage]:
    """Coleta Help Center + API Docs em paralelo, deduplicando por URL."""
    results = await asyncio.gather(
        HelpCenterCrawler(settings.helpcenter_base_url, settings).crawl(),
        ApiDocCrawler(settings.apidoc_base_url, settings).crawl(),
    )
    seen: set[str] = set()
    pages: list[RawPage] = []
    for page in (p for group in results for p in group):
        if page.url not in seen:
            seen.add(page.url)
            pages.append(page)
    return pages
