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

Requirements:
- Test understanding, not just memorization
- Mix of question types
- Clear correct answers with explanations

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
    
    async def suggest_resources(self, topics: list[dict], paper=None) -> list[dict]:
        """Suggest supplementary resources based on today's content."""
        topic_names = [t.get("name", "") for t in topics]
        concepts = []
        for t in topics:
            concepts.extend(t.get("key_concepts", []))
        
        paper_context = f'\nToday\'s paper: "{paper.title}"' if paper else ""
        
        prompt = f"""Suggest 5-7 supplementary resources for a data science doctoral student.

TOPICS: {', '.join(topic_names)}
CONCEPTS: {', '.join(concepts[:10])}
{paper_context}

Include tutorials, papers, videos, code repos, datasets. Format as JSON:
[{{"title": "...", "type": "tutorial|paper|video|code|dataset", "description": "...", "search_term": "..."}}]"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                temperature=0.5,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            
            return json.loads(content)
        except Exception as e:
            print(f"Error generating resources: {e}")
            return []
