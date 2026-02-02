/**
 * API Client for Daily Scholar Backend
 * 
 * This module provides typed functions to interact with the backend API.
 * All functions handle errors and return typed responses.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// =============================================================================
// TYPES
// =============================================================================

export interface Paper {
  title: string;
  authors: string[];
  abstract: string;
  url: string;
  pdf_url?: string;
  source: string;
  arxiv_id?: string;
  published_date?: string;
  categories: string[];
  relevance_score: number;
  primary_category: string;
}

export interface PaperSummary {
  summary: string;
  key_findings: string[];
  relevance_explanation: string;
  reading_approach: {
    estimated_minutes: number;
    focus_sections: string[];
    prerequisites: string[];
  };
  connections: string[];
}

export interface Topic {
  id: string;
  name: string;
  course_id: string;
  course_name: string;
  week_covered: number;
  key_concepts: string[];
  learning_objectives: string[];
}

export interface TopicReview {
  review_content: string;
  key_points: string[];
  connections: string[];
  practice_suggestions: string[];
}

export interface QuizQuestion {
  id: string;
  topic_id: string;
  topic_name?: string;
  course_name?: string;
  question_type: string;
  question_text: string;
  options?: string[];
  difficulty: string;
  points: number;
}

export interface QuizResult {
  is_correct: boolean;
  score: number;
  correct_answer: string;
  feedback: string;
}

export interface DailyContent {
  date: string;
  paper: Paper | null;
  paper_summary: PaperSummary | null;
  topic_reviews: Array<{
    topic: Topic;
    review: TopicReview;
  }>;
  quiz: {
    questions: QuizQuestion[];
    total_points: number;
  };
  resources: Array<{
    title: string;
    type: string;
    description: string;
    search_term: string;
  }>;
  estimated_time_minutes: number;
}

export interface ConfigStatus {
  environment_valid: boolean;
  interests_valid: boolean;
  courses_valid: boolean;
  errors: string[];
  interests_count: number;
  courses_count: number;
  topics_count: number;
}

// =============================================================================
// API FUNCTIONS
// =============================================================================

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `API error: ${response.status}`);
  }

  return response.json();
}

// -----------------------------------------------------------------------------
// Configuration
// -----------------------------------------------------------------------------

export async function getConfigStatus(): Promise<ConfigStatus> {
  return fetchAPI('/config/status');
}

export async function getInterests(): Promise<any> {
  return fetchAPI('/config/interests');
}

export async function getCourses(): Promise<any> {
  return fetchAPI('/config/courses');
}

// -----------------------------------------------------------------------------
// Papers
// -----------------------------------------------------------------------------

export async function discoverPapers(maxResults = 10, daysBack = 30): Promise<{ count: number; papers: Paper[] }> {
  return fetchAPI(`/papers/discover?max_results=${maxResults}&days_back=${daysBack}`);
}

export async function getDailyPaper(): Promise<{ paper: Paper | null; summary: PaperSummary | null }> {
  return fetchAPI('/papers/daily');
}

// -----------------------------------------------------------------------------
// Topics
// -----------------------------------------------------------------------------

export async function getAllTopics(): Promise<{ topics: Topic[] }> {
  return fetchAPI('/topics');
}

export async function getTopicReview(topicId: string): Promise<{ topic: Topic; review: TopicReview }> {
  return fetchAPI(`/topics/${topicId}/review`);
}

// -----------------------------------------------------------------------------
// Quiz
// -----------------------------------------------------------------------------

export async function generateQuiz(
  topicId: string,
  count = 5,
  difficulty = 'medium'
): Promise<{ topic: string; course: string; questions: QuizQuestion[]; total_points: number }> {
  return fetchAPI(`/quiz/generate/${topicId}?count=${count}&difficulty=${difficulty}`);
}

export async function submitAnswer(questionId: string, answer: string): Promise<QuizResult> {
  return fetchAPI(`/quiz/answer?question_id=${questionId}&answer=${encodeURIComponent(answer)}`, {
    method: 'POST',
  });
}

// -----------------------------------------------------------------------------
// Daily Content
// -----------------------------------------------------------------------------

export async function getDailyContent(): Promise<DailyContent> {
  return fetchAPI('/daily');
}

// -----------------------------------------------------------------------------
// Health
// -----------------------------------------------------------------------------

export async function checkHealth(): Promise<{ status: string; configuration: Record<string, string> }> {
  return fetchAPI('/health');
}
