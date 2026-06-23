"""
Paper Discovery Service for Daily Scholar

This service finds relevant research papers from multiple sources:
1. arXiv - Physics, Math, CS, Stats papers (completely free)
2. Semantic Scholar - Broad coverage, AI-powered recommendations
3. CORE - Aggregator of open access research papers
"""

import asyncio
import hashlib
from datetime import datetime, date, timedelta
from typing import Optional
import xml.etree.ElementTree as ET
import urllib.parse

import httpx

from ..config import get_settings
from ..database import DEFAULT_USER_ID, Topic, get_topics_for_scope

# default paper sources if the caller doesn't specify. lives here (not in a
# YAML) because the source list is operational, not per-topic; can be moved
# to UserSettings if we want per-user overrides later.
DEFAULT_SOURCES: tuple[str, ...] = ("arxiv", "semantic_scholar", "core")

# Semantic Scholar and CORE both go through cycles of 429/5xx storms and
# slow-response hangs. The shared client timeout (30s) means N parallel
# in-flight calls all wait the full 30s when those APIs are flapping —
# turning a transient external blip into a 30s+ cold-start dashboard hang.
# A tighter per-call timeout for known-flaky sources keeps total cycle time
# bounded by the worst-behaving source. arXiv is reliable enough to keep
# the default.
_FLAKY_EXTERNAL_TIMEOUT_SECONDS: float = 8.0


class Paper:
    """Normalized paper representation."""
    
    def __init__(
        self,
        title: str,
        authors: list[str],
        abstract: str,
        url: str,
        source: str,
        arxiv_id: Optional[str] = None,
        semantic_scholar_id: Optional[str] = None,
        doi: Optional[str] = None,
        pdf_url: Optional[str] = None,
        published_date: Optional[date] = None,
        categories: list[str] = None,
        citation_count: int = 0,
    ):
        self.title = title
        self.authors = authors
        self.abstract = abstract
        self.url = url
        self.source = source
        self.arxiv_id = arxiv_id
        self.semantic_scholar_id = semantic_scholar_id
        self.doi = doi
        self.pdf_url = pdf_url
        self.published_date = published_date
        self.categories = categories or []
        self.citation_count = citation_count
        self.relevance_score = 0.0
        self.primary_category = ""
    
    @property
    def unique_id(self) -> str:
        if self.arxiv_id:
            return f"arxiv:{self.arxiv_id}"
        if self.doi:
            return f"doi:{self.doi}"
        if self.semantic_scholar_id:
            return f"s2:{self.semantic_scholar_id}"
        return f"hash:{hashlib.md5(self.title.lower().encode()).hexdigest()[:12]}"
    
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "url": self.url,
            "source": self.source,
            "arxiv_id": self.arxiv_id,
            "semantic_scholar_id": self.semantic_scholar_id,
            "doi": self.doi,
            "pdf_url": self.pdf_url,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "categories": self.categories,
            "citation_count": self.citation_count,
            "relevance_score": self.relevance_score,
            "primary_category": self.primary_category,
        }


class PaperDiscoveryService:
    """Service for discovering relevant research papers."""

    def __init__(self, user_id: str = DEFAULT_USER_ID):
        # user_id drives topic-scope resolution. defaults to the local sentinel
        # so beta runs and tests work without auth wiring.
        self.user_id = user_id
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def close(self):
        await self.client.aclose()

    # ------------------------------------------------------------------
    # Topic-scope helpers
    # ------------------------------------------------------------------

    def _topics_in_scope(self) -> list[Topic]:
        """Active topics filtered by the user's silo/multi/all scope."""
        return get_topics_for_scope(self.user_id)

    @staticmethod
    def _aggregate_keywords(topics: list[Topic], *, limit: int | None = None) -> list[str]:
        """Dedup-keeping-order across topics, optionally truncated."""
        seen: set[str] = set()
        out: list[str] = []
        # iterate by weight descending so higher-priority topics' keywords sort first
        for topic in sorted(topics, key=lambda t: t.weight, reverse=True):
            for kw in topic.keywords or []:
                key = kw.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(kw)
                if limit and len(out) >= limit:
                    return out
        return out

    @staticmethod
    def _aggregate_categories(topics: list[Topic], *, limit: int | None = None) -> list[str]:
        """Dedup arxiv categories across topics, optionally truncated."""
        seen: set[str] = set()
        out: list[str] = []
        for topic in sorted(topics, key=lambda t: t.weight, reverse=True):
            for cat in topic.arxiv_categories or []:
                if cat in seen:
                    continue
                seen.add(cat)
                out.append(cat)
                if limit and len(out) >= limit:
                    return out
        return out

    @staticmethod
    def _scope_min_relevance(topics: list[Topic], fallback: float = 0.18) -> float:
        """Lowest threshold across active topics — most permissive choice."""
        values = [t.min_relevance for t in topics if t.min_relevance is not None]
        return min(values) if values else fallback

    @staticmethod
    def _scope_max_recency(topics: list[Topic], fallback: int = 30) -> int:
        """Widest recency window across active topics."""
        values = [t.recency_days for t in topics if t.recency_days]
        return max(values) if values else fallback
    
    # =========================================================================
    # ARXIV API
    # =========================================================================
    
    async def search_arxiv(
        self,
        query: str,
        max_results: int = 20,
        days_back: int = 30,
    ) -> list[Paper]:
        """Search arXiv for papers."""
        base_url = "https://export.arxiv.org/api/query"
        
        clean_query = query.replace(":", " ").replace("/", " ").strip()
        encoded_query = urllib.parse.quote(clean_query)
        url = f"{base_url}?search_query=all:{encoded_query}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
        
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            papers = self._parse_arxiv_response(response.text)
            
            cutoff_date = date.today() - timedelta(days=days_back)
            papers = [p for p in papers if p.published_date and p.published_date >= cutoff_date]
            return papers
            
        except httpx.HTTPError as e:
            print(f"arXiv API error: {e}")
            return []
    
    async def search_arxiv_by_category(
        self,
        category: str,
        max_results: int = 20,
        days_back: int = 30,
    ) -> list[Paper]:
        """Search arXiv by category (e.g., cs.LG, stat.ML)."""
        base_url = "https://export.arxiv.org/api/query"
        url = f"{base_url}?search_query=cat:{category}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
        
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            papers = self._parse_arxiv_response(response.text)
            
            cutoff_date = date.today() - timedelta(days=days_back)
            papers = [p for p in papers if p.published_date and p.published_date >= cutoff_date]
            return papers
            
        except httpx.HTTPError as e:
            print(f"arXiv category search error for {category}: {e}")
            return []
    
    def _parse_arxiv_response(self, xml_text: str) -> list[Paper]:
        """Parse arXiv API XML response into Paper objects."""
        papers = []
        namespaces = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        
        try:
            root = ET.fromstring(xml_text)
            
            for entry in root.findall("atom:entry", namespaces):
                id_elem = entry.find("atom:id", namespaces)
                arxiv_url = id_elem.text if id_elem is not None else ""
                arxiv_id = arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else None
                
                title_elem = entry.find("atom:title", namespaces)
                title = title_elem.text.strip().replace("\n", " ") if title_elem is not None else ""
                
                summary_elem = entry.find("atom:summary", namespaces)
                abstract = summary_elem.text.strip() if summary_elem is not None else ""
                
                authors = []
                for author in entry.findall("atom:author", namespaces):
                    name_elem = author.find("atom:name", namespaces)
                    if name_elem is not None:
                        authors.append(name_elem.text)
                
                published_elem = entry.find("atom:published", namespaces)
                published_date = None
                if published_elem is not None:
                    try:
                        published_date = datetime.fromisoformat(
                            published_elem.text.replace("Z", "+00:00")
                        ).date()
                    except ValueError:
                        pass
                
                categories = []
                for category in entry.findall("arxiv:primary_category", namespaces):
                    term = category.get("term")
                    if term:
                        categories.append(term)
                for category in entry.findall("atom:category", namespaces):
                    term = category.get("term")
                    if term and term not in categories:
                        categories.append(term)
                
                pdf_url = None
                for link in entry.findall("atom:link", namespaces):
                    if link.get("title") == "pdf":
                        pdf_url = link.get("href")
                        break
                
                paper = Paper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    url=arxiv_url,
                    source="arxiv",
                    arxiv_id=arxiv_id,
                    pdf_url=pdf_url,
                    published_date=published_date,
                    categories=categories,
                )
                papers.append(paper)
                
        except ET.ParseError as e:
            print(f"Error parsing arXiv XML: {e}")
        
        return papers
    
    # =========================================================================
    # SEMANTIC SCHOLAR API
    # =========================================================================
    
    async def search_semantic_scholar(
        self,
        query: str,
        max_results: int = 20,
        days_back: int = 30,
    ) -> list[Paper]:
        """Search Semantic Scholar for papers."""
        base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
        
        min_year = (datetime.now() - timedelta(days=days_back)).year
        
        params = {
            "query": query,
            "limit": max_results,
            "fields": "paperId,title,abstract,authors,year,venue,citationCount,openAccessPdf,externalIds",
            "year": f"{min_year}-",
        }
        
        headers = {}
        if self.settings.semantic_scholar_api_key:
            headers["x-api-key"] = self.settings.semantic_scholar_api_key
        
        try:
            response = await self.client.get(
                base_url,
                params=params,
                headers=headers,
                timeout=_FLAKY_EXTERNAL_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_semantic_scholar_response(data)

        except httpx.HTTPError as e:
            # fast-fail and let arXiv / CORE carry this cycle. logged once
            # per failed call (orchestrator runs many in parallel).
            print(f"Semantic Scholar skipped (flap or timeout): {e}")
            return []
    
    def _parse_semantic_scholar_response(self, data: dict) -> list[Paper]:
        """Parse Semantic Scholar API response into Paper objects."""
        papers = []
        
        for item in data.get("data", []):
            external_ids = item.get("externalIds", {}) or {}
            arxiv_id = external_ids.get("ArXiv")
            doi = external_ids.get("DOI")
            
            authors = [author.get("name", "") for author in item.get("authors", [])]
            
            pdf_info = item.get("openAccessPdf") or {}
            pdf_url = pdf_info.get("url")
            
            year = item.get("year")
            published_date = date(year, 1, 1) if year else None
            
            paper_id = item.get("paperId")
            url = f"https://www.semanticscholar.org/paper/{paper_id}"
            
            paper = Paper(
                title=item.get("title", ""),
                authors=authors,
                abstract=item.get("abstract") or "",
                url=url,
                source="semantic_scholar",
                semantic_scholar_id=paper_id,
                arxiv_id=arxiv_id,
                doi=doi,
                pdf_url=pdf_url,
                published_date=published_date,
                citation_count=item.get("citationCount", 0),
            )
            papers.append(paper)
        
        return papers
    
    # =========================================================================
    # CORE API
    # =========================================================================
    
    async def search_core(
        self,
        query: str,
        max_results: int = 20,
        days_back: int = 30,
    ) -> list[Paper]:
        """
        Search CORE for open access papers.
        
        CORE API documentation: https://core.ac.uk/documentation/api
        """
        if not self.settings.core_api_key:
            print("CORE API key not configured, skipping CORE search")
            return []
        
        base_url = "https://api.core.ac.uk/v3/search/works"
        
        params = {
            "q": query,
            "limit": max_results,
        }
        
        headers = {
            "Authorization": f"Bearer {self.settings.core_api_key}",
        }
        
        try:
            response = await self.client.get(
                base_url,
                params=params,
                headers=headers,
                timeout=_FLAKY_EXTERNAL_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_core_response(data, days_back)

        except httpx.HTTPError as e:
            print(f"CORE skipped (flap or timeout): {e}")
            return []
    
    def _parse_core_response(self, data: dict, days_back: int = 30) -> list[Paper]:
        """Parse CORE API response into Paper objects."""
        papers = []
        cutoff_date = date.today() - timedelta(days=days_back)
        
        for item in data.get("results", []):
            title = item.get("title", "")
            if not title:
                continue
            
            # Authors
            authors = []
            for author in item.get("authors", []):
                if isinstance(author, dict):
                    name = author.get("name", "")
                else:
                    name = str(author)
                if name:
                    authors.append(name)
            
            # Abstract
            abstract = item.get("abstract") or item.get("description") or ""
            
            # URLs
            url = None
            pdf_url = None
            
            if item.get("downloadUrl"):
                pdf_url = item.get("downloadUrl")
            if item.get("sourceFulltextUrls"):
                urls = item.get("sourceFulltextUrls", [])
                if urls:
                    pdf_url = urls[0]
            
            if item.get("links"):
                for link in item.get("links", []):
                    if isinstance(link, dict):
                        url = link.get("url")
                        break
                    else:
                        url = str(link)
                        break
            
            if not url:
                url = item.get("downloadUrl") or f"https://core.ac.uk/works/{item.get('id', '')}"
            
            # DOI
            doi = item.get("doi")
            
            # Published date
            published_date = None
            pub_date_str = item.get("publishedDate") or item.get("yearPublished")
            if pub_date_str:
                try:
                    if isinstance(pub_date_str, int):
                        published_date = date(pub_date_str, 1, 1)
                    elif len(str(pub_date_str)) == 4:
                        published_date = date(int(pub_date_str), 1, 1)
                    else:
                        published_date = datetime.fromisoformat(
                            str(pub_date_str).replace("Z", "+00:00").split("T")[0]
                        ).date()
                except (ValueError, TypeError):
                    pass
            
            # Filter by date (if we have one)
            if published_date and published_date < cutoff_date:
                continue
            
            # Subjects/categories
            categories = []
            for subject in item.get("subjects", []):
                if isinstance(subject, str):
                    categories.append(subject)
                elif isinstance(subject, dict):
                    categories.append(subject.get("name", ""))
            
            paper = Paper(
                title=title,
                authors=authors,
                abstract=abstract,
                url=url,
                source="core",
                doi=doi,
                pdf_url=pdf_url,
                published_date=published_date,
                categories=categories[:5],
                citation_count=item.get("citationCount", 0),
            )
            papers.append(paper)
        
        return papers
    
    # =========================================================================
    # RELEVANCE SCORING
    # =========================================================================
    
    def calculate_relevance_score(self, paper: Paper, topics: list[Topic] | None = None) -> float:
        """
        Score a paper against the user's active topic scope using max-aggregation.

        For each topic in scope:
          keyword_match_ratio = (# topic keywords found in title+abstract) / len(keywords)
          category_match_ratio = (# topic arxiv categories matching paper) / len(categories)
          topic_score = 0.6 * keyword_match_ratio + 0.4 * category_match_ratio   # 0..1

        Composite relevance = max(topic_scores) — i.e., the best-fit topic wins.
        This avoids penalizing single-strong-match papers, which the prior
        weighted-average approach did. Recency boost is applied on top.

        Topic weight isn't used in the score directly (since we're taking a max),
        but it IS used as a tiebreaker for primary_category attribution: when two
        topics match equally, the higher-weight one is named.

        Passing `topics` explicitly avoids a DB round-trip per paper when scoring
        a batch; otherwise it falls back to the user's current scope.
        """
        topics = topics if topics is not None else self._topics_in_scope()
        if not topics:
            paper.relevance_score = 0.0
            return 0.0

        searchable_text = f"{paper.title} {paper.abstract}".lower()
        best_match = 0.0
        best_topic_name = ""
        best_topic_weight = -1.0

        for topic in topics:
            keywords = topic.keywords or []
            cats = topic.arxiv_categories or []

            keyword_score = 0.0
            if keywords:
                hits = sum(1 for kw in keywords if kw.lower() in searchable_text)
                keyword_score = min(hits / len(keywords), 1.0)

            category_score = 0.0
            if cats:
                hits = sum(1 for c in cats if c in (paper.categories or []))
                category_score = min(hits / len(cats), 1.0)

            topic_match = 0.6 * keyword_score + 0.4 * category_score
            if topic_match == 0:
                continue

            tw = float(topic.weight or 1.0)
            # primary topic = strongest match, breaking ties by higher weight
            if (topic_match > best_match
                    or (topic_match == best_match and tw > best_topic_weight)):
                best_match = topic_match
                best_topic_name = topic.name
                best_topic_weight = tw

        score = best_match
        if paper.published_date:
            days_old = (date.today() - paper.published_date).days
            if days_old <= 7:
                score *= 1.1
            elif days_old <= 14:
                score *= 1.05

        score = min(score, 1.0)
        paper.relevance_score = score
        if best_topic_name and not paper.primary_category:
            paper.primary_category = best_topic_name
        return score
    
    # =========================================================================
    # MAIN DISCOVERY METHODS
    # =========================================================================
    
    async def discover_papers(
        self,
        max_results: int = 20,
        days_back: int | None = None,
        sources: list[str] | None = None,
    ) -> list[Paper]:
        """
        Discover relevant papers from configured sources, scored against the
        user's active topic scope.

        `days_back` defaults to the widest recency_days across topics in scope.
        `sources` defaults to DEFAULT_SOURCES.
        """
        topics = self._topics_in_scope()
        if not topics:
            print("paper_discovery: no topics in scope; nothing to search for")
            return []

        if sources is None:
            sources = list(DEFAULT_SOURCES)
        if days_back is None:
            days_back = self._scope_max_recency(topics)

        # aggregate search terms + arxiv categories across all topics in scope
        keywords = self._aggregate_keywords(topics, limit=5)
        categories = self._aggregate_categories(topics, limit=3)

        all_papers: list[Paper] = []
        tasks = []

        for source in sources:
            for term in keywords:
                if source == "arxiv":
                    tasks.append(self.search_arxiv(term, max_results=10, days_back=days_back))
                elif source == "semantic_scholar":
                    tasks.append(self.search_semantic_scholar(term, max_results=10, days_back=days_back))
                elif source == "core":
                    tasks.append(self.search_core(term, max_results=10, days_back=days_back))

        if "arxiv" in sources:
            for cat in categories:
                tasks.append(self.search_arxiv_by_category(cat, max_results=10, days_back=days_back))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_papers.extend(result)
            elif isinstance(result, Exception):
                print(f"Search error: {result}")

        # dedupe
        seen_ids: set[str] = set()
        unique_papers: list[Paper] = []
        for paper in all_papers:
            if paper.unique_id in seen_ids:
                continue
            seen_ids.add(paper.unique_id)
            unique_papers.append(paper)

        # score against the (already-loaded) topics — saves N DB hits
        for paper in unique_papers:
            self.calculate_relevance_score(paper, topics=topics)

        unique_papers.sort(key=lambda p: p.relevance_score, reverse=True)
        return unique_papers[:max_results]

    async def select_daily_paper(
        self,
        seen_ids: list[str] | None = None,
        days_back: int | None = None,
    ) -> Optional[Paper]:
        """Select the best paper for today's learning."""
        seen_ids = seen_ids or []

        topics = self._topics_in_scope()
        min_relevance = self._scope_min_relevance(topics)

        papers = await self.discover_papers(max_results=50, days_back=days_back)
        papers = [p for p in papers if p.unique_id not in seen_ids]
        papers = [p for p in papers if p.relevance_score >= min_relevance]

        if not papers:
            print(
                "No suitable papers found. "
                "Broaden the active topic scope, add keywords, or lower min_relevance."
            )
            return None

        return papers[0]
