"""
Daily Scholar Services

This package contains the core business logic:
- paper_discovery: Find relevant research papers
- content_generator: Generate summaries, reviews, quizzes
- quiz_engine: Manage quizzes and spaced repetition
- file_processor: Handle uploaded course materials
"""

from .paper_discovery import PaperDiscoveryService, Paper
from .content_generator import ContentGeneratorService

__all__ = [
    "PaperDiscoveryService",
    "Paper", 
    "ContentGeneratorService",
]
