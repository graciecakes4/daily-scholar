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

from ..config import get_settings, load_interests_config, get_interest_keywords, get_arxiv_categories


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
    
    def __init__(self):
        self.settings = get_settings()
        self.interests_config = load_interests_config()
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    
    async def close(self):
        await self.client.aclose()
    
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
        base_url = "http://export.arxiv.org/api/query"
        
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
        base_url = "http://export.arxiv.org/api/query"
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
            response = await self.client.get(base_url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            return self._parse_semantic_scholar_response(data)
            
        except httpx.HTTPError as e:
            print(f"Semantic Scholar API error: {e}")
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
            response = await self.client.get(base_url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            return self._parse_core_response(data, days_back)
            
        except httpx.HTTPError as e:
            print(f"CORE API error: {e}")
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
    
    def calculate_relevance_score(self, paper: Paper) -> float:
        """Calculate how relevant a paper is to user's interests."""
        score = 0.0
        max_score = 0.0
        
        interests = self.interests_config.get("interests", {})
        searchable_text = f"{paper.title} {paper.abstract}".lower()
        
        for category, weight_multiplier in [("primary", 2.0), ("secondary", 1.0), ("exploratory", 0.5)]:
            for interest in interests.get(category, []):
                interest_weight = interest.get("weight", 1.0) * weight_multiplier
                max_score += interest_weight
                
                keywords = interest.get("keywords", [])
                matches = sum(1 for kw in keywords if kw.lower() in searchable_text)
                if matches > 0:
                    keyword_score = min(matches / len(keywords), 1.0) if keywords else 0
                    score += keyword_score * interest_weight * 0.6
                
                arxiv_cats = interest.get("arxiv_categories", [])
                cat_matches = sum(1 for cat in arxiv_cats if cat in paper.categories)
                if cat_matches > 0:
                    cat_score = min(cat_matches / len(arxiv_cats), 1.0) if arxiv_cats else 0
                    score += cat_score * interest_weight * 0.4
                    
                    if cat_matches > 0 and not paper.primary_category:
                        paper.primary_category = interest.get("name", "General")
        
        if max_score > 0:
            score = score / max_score
        
        if paper.published_date:
            days_old = (date.today() - paper.published_date).days
            if days_old <= 7:
                score *= 1.1
            elif days_old <= 14:
                score *= 1.05
        
        score = min(score, 1.0)
        paper.relevance_score = score
        return score
    
    # =========================================================================
    # MAIN DISCOVERY METHODS
    # =========================================================================
    
    async def discover_papers(
        self,
        max_results: int = 20,
        days_back: int = 30,
        sources: list[str] = None,
    ) -> list[Paper]:
        """Discover relevant papers from all configured sources."""
        if sources is None:
            search_config = self.interests_config.get("search_config", {})
            sources = search_config.get("sources", ["arxiv", "semantic_scholar"])
        
        keywords = get_interest_keywords()
        all_papers: list[Paper] = []
        tasks = []
        
        # Search with top keywords
        search_terms = keywords[:5]
        
        for source in sources:
            for term in search_terms:
                if source == "arxiv":
                    tasks.append(self.search_arxiv(term, max_results=10, days_back=days_back))
                elif source == "semantic_scholar":
                    tasks.append(self.search_semantic_scholar(term, max_results=10, days_back=days_back))
                elif source == "core":
                    tasks.append(self.search_core(term, max_results=10, days_back=days_back))
        
        # Search by arXiv categories
        if "arxiv" in sources:
            categories = get_arxiv_categories()
            for cat in categories[:3]:
                tasks.append(self.search_arxiv_by_category(cat, max_results=10, days_back=days_back))
        
        # Run all searches in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                all_papers.extend(result)
            elif isinstance(result, Exception):
                print(f"Search error: {result}")
        
        # Deduplicate
        seen_ids = set()
        unique_papers = []
        for paper in all_papers:
            if paper.unique_id not in seen_ids:
                seen_ids.add(paper.unique_id)
                unique_papers.append(paper)
        
        # Calculate relevance scores
        for paper in unique_papers:
            self.calculate_relevance_score(paper)
        
        # Sort by relevance
        unique_papers.sort(key=lambda p: p.relevance_score, reverse=True)
        
        return unique_papers[:max_results]
    
    async def select_daily_paper(
        self,
        seen_ids: list[str] = None,
        days_back: int = 30,
    ) -> Optional[Paper]:
        """Select the best paper for today's learning."""
        seen_ids = seen_ids or []
        
        papers = await self.discover_papers(max_results=50, days_back=days_back)
        papers = [p for p in papers if p.unique_id not in seen_ids]
        
        min_relevance = self.interests_config.get("search_config", {}).get("min_relevance", 0.2)
        papers = [p for p in papers if p.relevance_score >= min_relevance]
        
        if not papers:
            print("No suitable papers found. Try broadening your interests or search criteria.")
            return None
        
        return papers[0]
