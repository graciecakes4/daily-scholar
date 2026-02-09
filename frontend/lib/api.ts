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

export interface Resource {
  title: string;
  type: string;
  description: string;
  url?: string;
  pdf_url?: string;
  search_term?: string;
  source?: string;
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
  resources: Resource[];
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

export interface RegeneratedQuiz {
  topics: string[];
  questions: QuizQuestion[];
  total_points: number;
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

export async function regenerateQuiz(
  count = 5,
  difficulty = 'medium'
): Promise<RegeneratedQuiz> {
  return fetchAPI(`/quiz/regenerate?count=${count}&difficulty=${difficulty}`, {
    method: 'POST',
  });
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

// -----------------------------------------------------------------------------
// Archive
// -----------------------------------------------------------------------------

export async function archivePaper(paper: any, summary?: any): Promise<{ id: number }> {
  return fetchAPI('/archive/papers', {
    method: 'POST',
    body: JSON.stringify({
      title: paper.title,
      authors: paper.authors,
      abstract: paper.abstract,
      url: paper.url,
      pdf_url: paper.pdf_url,
      source: paper.source,
      primary_category: paper.primary_category,
      relevance_score: paper.relevance_score,
      published_date: paper.published_date,
      arxiv_id: paper.arxiv_id,
      summary: summary?.summary,
      key_findings: summary?.key_findings,
    }),
  });
}

export async function archiveTopicReview(topic: any, review: any): Promise<{ id: number }> {
  return fetchAPI('/archive/topics', {
    method: 'POST',
    body: JSON.stringify({
      topic_id: topic.id,
      topic_name: topic.name,
      course_id: topic.course_id,
      course_name: topic.course_name,
      week_covered: topic.week_covered,
      review_content: review.review_content,
      key_points: review.key_points,
      connections: review.connections,
      practice_suggestions: review.practice_suggestions,
      key_concepts: topic.key_concepts,
    }),
  });
}

export async function archiveQuiz(
  topics: string[],
  questions: any[],
  results: Record<string, { correct: boolean; feedback: string }>,
  totalPoints: number
): Promise<{ id: number }> {
  const answeredQuestions = questions.map(q => ({
    ...q,
    result: results[q.id] || null,
  }));
  
  const scoreEarned = Object.values(results).filter(r => r.correct).length * 2; // Assuming 2 points per correct answer
  const percentage = (scoreEarned / totalPoints) * 100;
  
  return fetchAPI('/archive/quizzes', {
    method: 'POST',
    body: JSON.stringify({
      topics,
      total_questions: questions.length,
      total_points: totalPoints,
      score_earned: scoreEarned,
      percentage,
      questions: answeredQuestions,
    }),
  });
}

export async function getArchiveStats(): Promise<{
  papers: { total: number; completed: number };
  topics: { unique_topics: number; total_reviews: number };
  quizzes: { total: number; average_score: number };
}> {
  return fetchAPI('/archive/stats');
}
