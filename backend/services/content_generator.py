"""
Content Generator Service for Daily Scholar

This service uses Claude to generate:
1. Paper summaries - Plain language explanations of research papers
2. Topic reviews - Study material for course topics
3. Quiz questions - Various question types for testing knowledge
4. Supplementary content - Connections, examples, etc.

LEARNING NOTES:
- We use the Anthropic SDK for API calls (cleaner than raw HTTP)
- Prompts are carefully structured for consistent, useful output
- We request JSON responses for structured data (quizzes)
- Temperature is kept low for factual content, higher for creative content
"""

import json
from datetime import date
from typing import Optional
import anthropic
import httpx

from ..config import get_settings


class Paper:
    """Minimal Paper class for type hints (full version in paper_discovery.py)"""
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published_date: date


class ContentGeneratorService:
    """Service for generating learning content using Claude."""
    
    def __init__(self):
        self.settings = get_settings()
        self.client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        self.model = self.settings.claude_model
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Close the HTTP client."""
        await self.http_client.aclose()
    
    async def generate_paper_summary(self, paper) -> dict:
        """Generate a comprehensive summary of a research paper."""
        prompt = f"""You are helping a doctoral student in data science understand a research paper.

PAPER INFORMATION:
Title: {paper.title}
Authors: {', '.join(paper.authors[:5])}{'...' if len(paper.authors) > 5 else ''}
Published: {paper.published_date}
Categories: {', '.join(paper.categories[:5])}

Abstract:
{paper.abstract}

Please provide:
1. PLAIN LANGUAGE SUMMARY (2-3 paragraphs)
2. KEY FINDINGS (3-5 bullet points)
3. RELEVANCE TO DATA SCIENCE & ML
4. SUGGESTED READING APPROACH (time estimate, focus sections, prerequisites)
5. CONNECTIONS to other topics

Format as JSON:
{{
    "summary": "plain language summary...",
    "key_findings": ["finding 1", "finding 2"],
    "relevance_explanation": "why this matters...",
    "reading_approach": {{"estimated_minutes": 30, "focus_sections": [], "prerequisites": []}},
    "connections": ["related topic 1", "related topic 2"]
}}"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            return json.loads(content)
        except Exception as e:
            print(f"Error generating paper summary: {e}")
            return {"summary": "", "key_findings": [], "relevance_explanation": "", 
                    "reading_approach": {}, "connections": []}
    
    async def generate_topic_review(self, topic: dict, course: dict, 
                                     previous_performance: Optional[dict] = None) -> dict:
        """Generate a topic review for studying."""
        performance_context = ""
        if previous_performance:
            if previous_performance.get("average_score", 1.0) < 0.7:
                performance_context = "\nNote: Student has struggled with this topic. Focus on fundamentals."
            elif previous_performance.get("streak", 0) >= 3:
                performance_context = "\nNote: Student doing well. Include advanced material."
        
        prompt = f"""You are a knowledgeable tutor helping a doctoral student review a topic.

COURSE: {course.get('name', 'Unknown Course')}
TOPIC: {topic.get('name', 'Unknown Topic')}
KEY CONCEPTS: {', '.join(topic.get('key_concepts', []))}
LEARNING OBJECTIVES: {', '.join(topic.get('learning_objectives', []))}
{performance_context}

Provide a comprehensive review including:
1. REVIEW CONTENT (3-5 paragraphs) - Clear explanation with examples
2. KEY POINTS (5-7 items) - Most important takeaways
3. CONNECTIONS - How this relates to other topics
4. PRACTICE SUGGESTIONS - Ways to apply this knowledge

Format as JSON:
{{
    "review_content": "detailed review...",
    "key_points": ["point 1", "point 2"],
    "connections": ["connection 1"],
    "practice_suggestions": ["suggestion 1"]
}}"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2500,
                temperature=0.4,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            return json.loads(content)
        except Exception as e:
            print(f"Error generating topic review: {e}")
            return {"review_content": "", "key_points": [], "connections": [], 
                    "practice_suggestions": []}
    
    async def generate_quiz_questions(self, topic: dict, course: dict, count: int = 5,
                                       question_types: list[str] = None, 
                                       difficulty: str = "medium") -> list[dict]:
        """Generate quiz questions for a topic."""
        if question_types is None:
            question_types = ["multiple_choice", "short_answer", "true_false"]
        
        prompt = f"""Create {count} quiz questions to test understanding.

COURSE: {course.get('name', '')}
TOPIC: {topic.get('name', '')}
DIFFICULTY: {difficulty}
KEY CONCEPTS: {', '.join(topic.get('key_concepts', []))}
QUESTION TYPES: {', '.join(question_types)}

CRITICAL REQUIREMENTS:
- Test CONCEPTUAL understanding, not numerical calculations
- Do NOT create questions requiring math computations (no "calculate the weighted sum", no "what is the output value")
- Focus on: definitions, comparisons, reasoning about behavior, identifying correct/incorrect statements, explaining why something works
- For multiple choice: all options should be plausible but only one clearly correct
- Ensure the correct_answer EXACTLY matches one of the options

GOOD question types:
- "Which of the following best describes...?"
- "What is the PRIMARY purpose of...?"
- "Which statement about X is TRUE/FALSE?"
- "In what scenario would you use X instead of Y?"
- "What problem does X solve?"

BAD question types (AVOID):
- "Calculate the output when..."
- "What is the value of...?"
- "Given weights [0.5, 0.3], compute..."

Format as JSON array:
[
    {{
        "question_type": "multiple_choice",
        "question_text": "What is...?",
        "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
        "correct_answer": "B) ...",
        "explanation": "This is correct because...",
        "concept_tested": "specific concept"
    }}
]"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=3000,
                temperature=0.6,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            questions = json.loads(content)
            
            for i, q in enumerate(questions):
                q["id"] = f"{topic['id']}_q{i+1}_{date.today().isoformat()}"
                q["topic_id"] = topic["id"]
                q["course_id"] = course["id"]
                q["difficulty"] = difficulty
                q["points"] = {"easy": 1, "medium": 2, "hard": 3}.get(difficulty, 1)
            
            return questions
        except Exception as e:
            print(f"Error generating quiz questions: {e}")
            return []
    
    async def evaluate_answer(self, question: dict, user_answer: str) -> dict:
        """Evaluate a user's answer to a quiz question."""
        question_type = question.get("question_type", "")
        correct_answer = question.get("correct_answer", "")
        
        # Simple evaluation for MC/TF
        if question_type in ["multiple_choice", "true_false"]:
            user_norm = user_answer.strip().lower()
            correct_norm = correct_answer.strip().lower()
            
            if question_type == "multiple_choice":
                is_correct = user_norm[0] == correct_norm[0] if user_norm and correct_norm else False
            else:
                is_correct = user_norm in correct_norm or correct_norm in user_norm
            
            return {
                "is_correct": is_correct,
                "score": 1.0 if is_correct else 0.0,
                "correct_answer": correct_answer,
                "feedback": question.get("explanation", "") if is_correct else 
                           f"Correct answer: {correct_answer}\n{question.get('explanation', '')}"
            }
        
        # Use Claude for open-ended answers
        prompt = f"""Evaluate this student answer:

QUESTION: {question.get('question_text', '')}
EXPECTED ANSWER: {correct_answer}
STUDENT'S ANSWER: {user_answer}

Be generous with partial credit. Format as JSON:
{{"is_correct": true/false, "score": 0.0-1.0, "feedback": "constructive feedback"}}"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            
            result = json.loads(content)
            result["correct_answer"] = correct_answer
            return result
        except Exception as e:
            return {"is_correct": False, "score": 0.0, "correct_answer": correct_answer,
                    "feedback": "Unable to evaluate automatically."}
    
    async def _search_semantic_scholar(self, query: str, limit: int = 3) -> list[dict]:
        """Search Semantic Scholar for papers matching the query."""
        try:
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            params = {
                "query": query,
                "limit": limit,
                "fields": "paperId,title,authors,year,url,citationCount,openAccessPdf"
            }
            
            headers = {}
            if self.settings.semantic_scholar_api_key:
                headers["x-api-key"] = self.settings.semantic_scholar_api_key
            
            response = await self.http_client.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                results = []
                for paper in data.get("data", [])[:limit]:
                    pdf_url = None
                    if paper.get("openAccessPdf"):
                        pdf_url = paper["openAccessPdf"].get("url")
                    
                    results.append({
                        "title": paper.get("title", ""),
                        "authors": [a.get("name", "") for a in paper.get("authors", [])[:3]],
                        "year": paper.get("year"),
                        "url": paper.get("url") or f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}",
                        "pdf_url": pdf_url,
                        "citations": paper.get("citationCount", 0),
                        "source": "semantic_scholar"
                    })
                return results
            else:
                print(f"Semantic Scholar search error: {response.status_code}")
                return []
        except Exception as e:
            print(f"Semantic Scholar search exception: {e}")
            return []
    
    async def _search_arxiv(self, query: str, limit: int = 3) -> list[dict]:
        """Search arXiv for papers matching the query."""
        try:
            import urllib.parse
            
            # Clean the query for arXiv
            clean_query = query.replace(":", " ").replace('"', "")
            encoded_query = urllib.parse.quote(clean_query)
            
            url = f"https://export.arxiv.org/api/query?search_query=all:{encoded_query}&start=0&max_results={limit}&sortBy=relevance"
            
            response = await self.http_client.get(url)
            
            if response.status_code == 200:
                import xml.etree.ElementTree as ET
                
                root = ET.fromstring(response.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                
                results = []
                for entry in root.findall("atom:entry", ns):
                    title = entry.find("atom:title", ns)
                    title_text = title.text.strip().replace("\n", " ") if title is not None else ""
                    
                    authors = []
                    for author in entry.findall("atom:author", ns):
                        name = author.find("atom:name", ns)
                        if name is not None:
                            authors.append(name.text)
                    
                    # Get links
                    abstract_url = None
                    pdf_url = None
                    for link in entry.findall("atom:link", ns):
                        if link.get("type") == "text/html":
                            abstract_url = link.get("href")
                        elif link.get("title") == "pdf":
                            pdf_url = link.get("href")
                    
                    if not abstract_url:
                        id_elem = entry.find("atom:id", ns)
                        if id_elem is not None:
                            abstract_url = id_elem.text
                    
                    results.append({
                        "title": title_text,
                        "authors": authors[:3],
                        "url": abstract_url,
                        "pdf_url": pdf_url,
                        "source": "arxiv"
                    })
                
                return results
            else:
                print(f"arXiv search error: {response.status_code}")
                return []
        except Exception as e:
            print(f"arXiv search exception: {e}")
            return []
    
    async def _get_github_repos(self, query: str, limit: int = 2) -> list[dict]:
        """Search GitHub for relevant repositories."""
        try:
            url = "https://api.github.com/search/repositories"
            params = {
                "q": f"{query} in:name,description,readme",
                "sort": "stars",
                "order": "desc",
                "per_page": limit
            }
            
            headers = {"Accept": "application/vnd.github.v3+json"}
            
            response = await self.http_client.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                results = []
                for repo in data.get("items", [])[:limit]:
                    results.append({
                        "title": repo.get("full_name", ""),
                        "description": repo.get("description", "")[:200] if repo.get("description") else "",
                        "url": repo.get("html_url", ""),
                        "stars": repo.get("stargazers_count", 0),
                        "source": "github"
                    })
                return results
            else:
                print(f"GitHub search error: {response.status_code}")
                return []
        except Exception as e:
            print(f"GitHub search exception: {e}")
            return []
    
    async def suggest_resources(self, topics: list[dict], paper=None) -> list[dict]:
        """Suggest supplementary resources with real URLs based on today's content."""
        topic_names = [t.get("name", "") for t in topics]
        concepts = []
        for t in topics:
            concepts.extend(t.get("key_concepts", []))
        
        resources = []
        
        # 1. Search for relevant papers on Semantic Scholar
        for topic in topics[:2]:  # Limit to avoid rate limits
            topic_name = topic.get("name", "")
            if topic_name:
                papers = await self._search_semantic_scholar(topic_name, limit=2)
                for p in papers:
                    resources.append({
                        "title": p["title"],
                        "type": "paper",
                        "description": f"By {', '.join(p['authors'][:2])}{'...' if len(p['authors']) > 2 else ''}" + 
                                      (f" ({p['year']})" if p.get('year') else "") +
                                      (f" - {p['citations']} citations" if p.get('citations') else ""),
                        "url": p["url"],
                        "pdf_url": p.get("pdf_url"),
                        "source": "semantic_scholar"
                    })
        
        # 2. Search for relevant papers on arXiv
        if concepts:
            # Pick a few key concepts to search
            search_concepts = concepts[:3]
            for concept in search_concepts[:1]:  # Just one arXiv search to avoid rate limits
                arxiv_papers = await self._search_arxiv(concept, limit=2)
                for p in arxiv_papers:
                    # Avoid duplicates
                    if not any(r["title"].lower() == p["title"].lower() for r in resources):
                        resources.append({
                            "title": p["title"],
                            "type": "paper",
                            "description": f"By {', '.join(p['authors'][:2])}{'...' if len(p['authors']) > 2 else ''}",
                            "url": p["url"],
                            "pdf_url": p.get("pdf_url"),
                            "source": "arxiv"
                        })
        
        # 3. Search GitHub for relevant code/tutorials
        for topic in topics[:1]:
            topic_name = topic.get("name", "").replace("Introduction to ", "").replace(" and ", " ")
            if topic_name:
                repos = await self._get_github_repos(f"{topic_name} tutorial python", limit=2)
                for repo in repos:
                    resources.append({
                        "title": repo["title"],
                        "type": "code",
                        "description": repo["description"] + (f" ⭐ {repo['stars']}" if repo.get('stars') else ""),
                        "url": repo["url"],
                        "source": "github"
                    })
        
        # 4. Add some well-known static resources based on topics
        static_resources = self._get_static_resources(topic_names, concepts)
        resources.extend(static_resources)
        
        # Deduplicate and limit
        seen_titles = set()
        unique_resources = []
        for r in resources:
            title_lower = r["title"].lower()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_resources.append(r)
        
        return unique_resources[:10]  # Return top 10 resources
    
    def _get_static_resources(self, topic_names: list[str], concepts: list[str]) -> list[dict]:
        """Get well-known static resources based on topics."""
        resources = []
        
        # Convert to lowercase for matching
        topics_lower = " ".join(topic_names).lower()
        concepts_lower = " ".join(concepts).lower()
        all_text = topics_lower + " " + concepts_lower
        
        # Python basics
        if any(term in all_text for term in ["python", "syntax", "programming", "functions", "classes"]):
            resources.append({
                "title": "Python Official Tutorial",
                "type": "tutorial",
                "description": "Official Python documentation tutorial - comprehensive guide to Python basics",
                "url": "https://docs.python.org/3/tutorial/",
                "source": "official"
            })
        
        # Deep learning / Neural networks
        if any(term in all_text for term in ["neural network", "deep learning", "ann", "mlp", "backpropagation"]):
            resources.append({
                "title": "3Blue1Brown Neural Networks",
                "type": "video",
                "description": "Excellent visual explanations of neural networks and deep learning concepts",
                "url": "https://www.youtube.com/playlist?list=PLZHQObOWTQDNU6R1_67000Dx_ZCJB-3pi",
                "source": "youtube"
            })
            resources.append({
                "title": "Deep Learning Book (Goodfellow et al.)",
                "type": "book",
                "description": "The definitive textbook on deep learning - free online version",
                "url": "https://www.deeplearningbook.org/",
                "source": "official"
            })
        
        # NLP / Transformers
        if any(term in all_text for term in ["nlp", "natural language", "transformer", "attention", "bert", "gpt"]):
            resources.append({
                "title": "Hugging Face NLP Course",
                "type": "tutorial",
                "description": "Free course covering transformers, fine-tuning, and modern NLP techniques",
                "url": "https://huggingface.co/learn/nlp-course",
                "source": "huggingface"
            })
        
        # Data Engineering / Spark / Pipelines
        if any(term in all_text for term in ["data engineering", "spark", "pipeline", "etl", "hadoop", "distributed"]):
            resources.append({
                "title": "Spark: The Definitive Guide (Free Chapters)",
                "type": "book",
                "description": "Comprehensive guide to Apache Spark by the creators",
                "url": "https://github.com/databricks/Spark-The-Definitive-Guide",
                "source": "github"
            })
        
        # Machine Learning general
        if any(term in all_text for term in ["machine learning", "ml", "supervised", "classification", "regression"]):
            resources.append({
                "title": "Scikit-learn User Guide",
                "type": "tutorial",
                "description": "Official documentation with excellent tutorials on ML algorithms",
                "url": "https://scikit-learn.org/stable/user_guide.html",
                "source": "official"
            })
        
        # TensorFlow / Keras
        if any(term in all_text for term in ["tensorflow", "keras", "neural", "deep learning"]):
            resources.append({
                "title": "TensorFlow Tutorials",
                "type": "tutorial",
                "description": "Official TensorFlow tutorials covering basics to advanced topics",
                "url": "https://www.tensorflow.org/tutorials",
                "source": "official"
            })
        
        # PyTorch
        if any(term in all_text for term in ["pytorch", "torch"]):
            resources.append({
                "title": "PyTorch Tutorials",
                "type": "tutorial",
                "description": "Official PyTorch tutorials with hands-on examples",
                "url": "https://pytorch.org/tutorials/",
                "source": "official"
            })
        
        return resources
