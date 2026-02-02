"""
Paper Discovery Service for Daily Scholar

This service finds relevant research papers from multiple sources:
1. arXiv - Physics, Math, CS, Stats papers (completely free)
2. Semantic Scholar - Broad coverage, AI-powered recommendations
3. CORE - Aggregator of open access papers (optional)

LEARNING NOTES:
- We use httpx for async HTTP requests (faster than requests library)
- Each source has a different API format, so we normalize to a common structure
- Relevance scoring combines multiple factors: recency, keyword matches, citations
- We track "seen" papers to avoid showing duplicates

HOW TO EXTEND:
- Add new paper sources by creating a new async method
- Modify relevance scoring in calculate_relevance_score()
- Add new filtering criteria in filter_papers()
"""

import asyncio
import hashlib
from datetime import datetime, date, timedelta
from typing import Optional
import xml.etree.ElementTree as ET
import json

import httpx

from ..config import get_settings, load_interests_config, get_interest_keywords, get_arxiv_categories


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class Paper:
    """
    Normalized paper representation.
    
    Different APIs return different formats, so we convert everything
    to this common structure for easier processing.
    """
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
        """Generate a unique ID for deduplication."""
        if self.arxiv_id:
            return f"arxiv:{self.arxiv_id}"
        if self.doi:
            return f"doi:{self.doi}"
        if self.semantic_scholar_id:
            return f"s2:{self.semantic_scholar_id}"
        # Fallback: hash of title
        return f"hash:{hashlib.md5(self.title.lower().encode()).hexdigest()[:12]}"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
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


# =============================================================================
# PAPER DISCOVERY SERVICE
# =============================================================================

class PaperDiscoveryService:
    """
    Service for discovering relevant research papers.
    
    Usage:
        service = PaperDiscoveryService()
        papers = await service.discover_papers(max_results=10)
        best_paper = await service.select_daily_paper(seen_ids=["arxiv:2301.01234"])
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.interests_config = load_interests_config()
        
        # HTTP client with reasonable timeouts
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
        )
    
    async def close(self):
        """Close the HTTP client."""
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
        """
        Search arXiv for papers.
        
        arXiv API documentation: https://arxiv.org/help/api/
        
        Args:
            query: Search query (supports arXiv query syntax)
            max_results: Maximum papers to return
            days_back: Only include papers from last N days
            
        Returns:
            List of Paper objects
        """
        # arXiv API endpoint
        base_url = "http://export.arxiv.org/api/query"
        
        # Calculate date range
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
        
        # Build query - search in title and abstract
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        
        try:
            response = await self.client.get(base_url, params=params)
            response.raise_for_status()
            
            # Parse XML response
            papers = self._parse_arxiv_response(response.text)
            
            # Filter by date
            cutoff_date = date.today() - timedelta(days=days_back)
            papers = [p for p in papers if p.published_date and p.published_date >= cutoff_date]
            
            return papers
            
        except httpx.HTTPError as e:
            print(f"arXiv API error: {e}")
            return []
    
    def _parse_arxiv_response(self, xml_text: str) -> list[Paper]:
        """Parse arXiv API XML response into Paper objects."""
        papers = []
        
        # arXiv uses Atom namespace
        namespaces = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        
        try:
            root = ET.fromstring(xml_text)
            
            for entry in root.findall("atom:entry", namespaces):
                # Extract paper ID from the URL
                id_elem = entry.find("atom:id", namespaces)
                arxiv_url = id_elem.text if id_elem is not None else ""
                arxiv_id = arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else None
                
                # Title
                title_elem = entry.find("atom:title", namespaces)
                title = title_elem.text.strip().replace("\n", " ") if title_elem is not None else ""
                
                # Abstract
                summary_elem = entry.find("atom:summary", namespaces)
                abstract = summary_elem.text.strip() if summary_elem is not None else ""
                
                # Authors
                authors = []
                for author in entry.findall("atom:author", namespaces):
                    name_elem = author.find("atom:name", namespaces)
                    if name_elem is not None:
                        authors.append(name_elem.text)
                
                # Published date
                published_elem = entry.find("atom:published", namespaces)
                published_date = None
                if published_elem is not None:
                    try:
                        published_date = datetime.fromisoformat(
                            published_elem.text.replace("Z", "+00:00")
                        ).date()
                    except ValueError:
                        pass
                
                # Categories
                categories = []
                for category in entry.findall("arxiv:primary_category", namespaces):
                    term = category.get("term")
                    if term:
                        categories.append(term)
                for category in entry.findall("atom:category", namespaces):
                    term = category.get("term")
                    if term and term not in categories:
                        categories.append(term)
                
                # PDF link
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
        """
        Search Semantic Scholar for papers.
        
        API documentation: https://api.semanticscholar.org/
        
        Args:
            query: Search query
            max_results: Maximum papers to return
            days_back: Only include papers from last N days
            
        Returns:
            List of Paper objects
        """
        base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
        
        # Calculate year filter (S2 uses year, not exact date)
        min_year = (datetime.now() - timedelta(days=days_back)).year
        
        params = {
            "query": query,
            "limit": max_results,
            "fields": "paperId,title,abstract,authors,year,venue,citationCount,openAccessPdf,externalIds",
            "year": f"{min_year}-",  # Papers from min_year onwards
            "openAccessPdf": "",  # Only open access papers
        }
        
        headers = {}
        if self.settings.semantic_scholar_api_key:
            headers["x-api-key"] = self.settings.semantic_scholar_api_key
        
        try:
            response = await self.client.get(base_url, params=params, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            papers = self._parse_semantic_scholar_response(data)
            
            return papers
            
        except httpx.HTTPError as e:
            print(f"Semantic Scholar API error: {e}")
            return []
    
    def _parse_semantic_scholar_response(self, data: dict) -> list[Paper]:
        """Parse Semantic Scholar API response into Paper objects."""
        papers = []
        
        for item in data.get("data", []):
            # Extract external IDs
            external_ids = item.get("externalIds", {}) or {}
            arxiv_id = external_ids.get("ArXiv")
            doi = external_ids.get("DOI")
            
            # Authors
            authors = [
                author.get("name", "")
                for author in item.get("authors", [])
            ]
            
            # PDF URL from openAccessPdf
            pdf_info = item.get("openAccessPdf") or {}
            pdf_url = pdf_info.get("url")
            
            # Published date (only year available)
            year = item.get("year")
            published_date = date(year, 1, 1) if year else None
            
            # Paper URL
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
    # RELEVANCE SCORING
    # =========================================================================
    
    def calculate_relevance_score(self, paper: Paper) -> float:
        """
        Calculate how relevant a paper is to user's interests.
        
        Scoring factors:
        - Keyword matches in title and abstract
        - Category matches with arxiv_categories
        - Interest weights from config
        - Recency bonus
        - Citation velocity (citations / age)
        
        Returns:
            Score from 0 to 1
        """
        score = 0.0
        max_score = 0.0
        
        # Get interests config
        interests = self.interests_config.get("interests", {})
        
        # Combine text for searching
        searchable_text = f"{paper.title} {paper.abstract}".lower()
        
        # Score each interest category
        for category, weight_multiplier in [("primary", 2.0), ("secondary", 1.0), ("exploratory", 0.5)]:
            for interest in interests.get(category, []):
                interest_weight = interest.get("weight", 1.0) * weight_multiplier
                max_score += interest_weight
                
                # Keyword matching
                keywords = interest.get("keywords", [])
                matches = sum(1 for kw in keywords if kw.lower() in searchable_text)
                if matches > 0:
                    keyword_score = min(matches / len(keywords), 1.0) if keywords else 0
                    score += keyword_score * interest_weight * 0.6  # 60% weight to keywords
                
                # Category matching
                arxiv_cats = interest.get("arxiv_categories", [])
                cat_matches = sum(1 for cat in arxiv_cats if cat in paper.categories)
                if cat_matches > 0:
                    cat_score = min(cat_matches / len(arxiv_cats), 1.0) if arxiv_cats else 0
                    score += cat_score * interest_weight * 0.4  # 40% weight to categories
                    
                    # Track primary category for this paper
                    if cat_matches > 0 and not paper.primary_category:
                        paper.primary_category = interest.get("name", "General")
        
        # Normalize score
        if max_score > 0:
            score = score / max_score
        
        # Recency bonus (up to 10% boost for very recent papers)
        if paper.published_date:
            days_old = (date.today() - paper.published_date).days
            if days_old <= 7:
                score *= 1.1
            elif days_old <= 14:
                score *= 1.05
        
        # Cap at 1.0
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
        """
        Discover relevant papers from all configured sources.
        
        Args:
            max_results: Maximum papers to return (total)
            days_back: Only include papers from last N days
            sources: Which sources to use (default: all configured)
            
        Returns:
            List of Paper objects, sorted by relevance
        """
        # Default to configured sources
        if sources is None:
            search_config = self.interests_config.get("search_config", {})
            sources = search_config.get("sources", ["arxiv", "semantic_scholar"])
        
        # Get search keywords
        keywords = get_interest_keywords()
        
        # Search each source in parallel
        all_papers: list[Paper] = []
        
        # Create search tasks
        tasks = []
        
        # Search with top keywords (not all, to avoid API limits)
        search_terms = keywords[:5]  # Top 5 keywords
        
        for source in sources:
            for term in search_terms:
                if source == "arxiv":
                    tasks.append(self.search_arxiv(term, max_results=10, days_back=days_back))
                elif source == "semantic_scholar":
                    tasks.append(self.search_semantic_scholar(term, max_results=10, days_back=days_back))
        
        # Also search by arXiv categories
        if "arxiv" in sources:
            categories = get_arxiv_categories()
            for cat in categories[:3]:  # Top 3 categories
                tasks.append(self.search_arxiv(f"cat:{cat}", max_results=10, days_back=days_back))
        
        # Run all searches in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect results
        for result in results:
            if isinstance(result, list):
                all_papers.extend(result)
            elif isinstance(result, Exception):
                print(f"Search error: {result}")
        
        # Deduplicate by unique_id
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
        
        # Return top results
        return unique_papers[:max_results]
    
    async def select_daily_paper(
        self,
        seen_ids: list[str] = None,
        days_back: int = 30,
    ) -> Optional[Paper]:
        """
        Select the best paper for today's learning.
        
        Args:
            seen_ids: List of unique_ids for papers already shown
            days_back: How far back to search
            
        Returns:
            The selected Paper, or None if no suitable paper found
        """
        seen_ids = seen_ids or []
        
        # Get candidate papers
        papers = await self.discover_papers(max_results=50, days_back=days_back)
        
        # Filter out seen papers
        papers = [p for p in papers if p.unique_id not in seen_ids]
        
        # Filter by minimum relevance
        min_relevance = self.interests_config.get("search_config", {}).get("min_relevance", 0.3)
        papers = [p for p in papers if p.relevance_score >= min_relevance]
        
        if not papers:
            print("No suitable papers found. Try broadening your interests or search criteria.")
            return None
        
        # Select the top paper
        # Could implement more sophisticated selection (diversity, etc.) here
        return papers[0]


# =============================================================================
# QUICK TESTING
# =============================================================================

async def test_discovery():
    """Quick test of paper discovery."""
    service = PaperDiscoveryService()
    
    try:
        print("Searching for papers...")
        papers = await service.discover_papers(max_results=5, days_back=7)
        
        print(f"\nFound {len(papers)} papers:\n")
        for i, paper in enumerate(papers, 1):
            print(f"{i}. {paper.title[:80]}...")
            print(f"   Source: {paper.source}, Score: {paper.relevance_score:.2f}")
            print(f"   Category: {paper.primary_category}")
            print(f"   URL: {paper.url}\n")
            
    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(test_discovery())
