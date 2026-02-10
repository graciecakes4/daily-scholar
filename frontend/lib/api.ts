/**
 * API Client for Daily Scholar Backend
 * Full paper lifecycle with seen tracking, PDF upload, and archives.
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
  semantic_scholar_id?: string;
  doi?: string;
  published_date?: string;
  categories: string[];
  relevance_score: number;
  primary_category: string;
  unique_id?: string;
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

export interface ArchivedPaper extends Paper {
  id: number;
  summary?: string;
  key_findings?: string[];
  user_notes?: string;
  user_rating?: number;
  read_status: 'unread' | 'reading' | 'completed';
  has_local_pdf: boolean;
  linked_topic_ids?: string[];
  archived_at: string;
}

export interface SeenPaper {
  id: number;
  unique_id: string;
  title: string;
  authors: string[];
  source: string;
  url: string;
  shown_date: string;
  was_archived: boolean;
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

export interface ArchivedTopic {
  id: number;
  topic_id: string;
  topic_name: string;
  course_id: string;
  course_name: string;
  review_count: number;
  confidence_level?: number;
  user_notes?: string;
  linked_paper_ids?: number[];
  last_reviewed_at: string;
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

export interface ArchivedQuiz {
  id: number;
  topics: string[];
  total_questions: number;
  total_points: number;
  score_earned: number;
  percentage: number;
  taken_at: string;
}

export interface Resource {
  title: string;
  type: string;
  description: string;
  url?: string;
  pdf_url?: string;
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

export interface UserStats {
  lifetime: {
    papers_seen: number;
    papers_archived: number;
    papers_completed: number;
    topics_reviewed: number;
    quizzes_taken: number;
    quiz_accuracy: number;
  };
  papers_by_status: {
    unread: number;
    reading: number;
    completed: number;
  };
  streaks: {
    current: number;
    longest: number;
    last_activity: string | null;
  };
  recent_papers: Array<{
    title: string;
    source: string;
    shown_date: string;
  }>;
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
// Health & Config
// -----------------------------------------------------------------------------

export async function checkHealth(): Promise<{ status: string; configuration: Record<string, string> }> {
  return fetchAPI('/health');
}

export async function getConfigStatus(): Promise<any> {
  return fetchAPI('/config/status');
}

// -----------------------------------------------------------------------------
// User Stats
// -----------------------------------------------------------------------------

export async function getUserStats(): Promise<UserStats> {
  return fetchAPI('/stats');
}

// -----------------------------------------------------------------------------
// Paper Discovery
// -----------------------------------------------------------------------------

export async function discoverPapers(maxResults = 10, daysBack = 30): Promise<{ count: number; papers: Paper[]; filtered_seen: number }> {
  return fetchAPI(`/papers/discover?max_results=${maxResults}&days_back=${daysBack}`);
}

export async function getDailyPaper(): Promise<{ paper: Paper | null; summary: PaperSummary | null }> {
  return fetchAPI('/papers/daily');
}

export async function getPaperHistory(limit = 50, offset = 0): Promise<{ papers: SeenPaper[]; total: number }> {
  return fetchAPI(`/papers/history?limit=${limit}&offset=${offset}`);
}

// -----------------------------------------------------------------------------
// Paper Archive
// -----------------------------------------------------------------------------

export async function archivePaper(paper: Paper, summary?: PaperSummary): Promise<{ id: number }> {
  return fetchAPI('/archive/papers', {
    method: 'POST',
    body: JSON.stringify({
      unique_id: paper.unique_id || `hash:${paper.title.toLowerCase().slice(0, 20)}`,
      title: paper.title,
      authors: paper.authors,
      abstract: paper.abstract,
      url: paper.url,
      pdf_url: paper.pdf_url,
      source: paper.source,
      primary_category: paper.primary_category,
      categories: paper.categories,
      relevance_score: paper.relevance_score,
      published_date: paper.published_date,
      arxiv_id: paper.arxiv_id,
      semantic_scholar_id: paper.semantic_scholar_id,
      doi: paper.doi,
      summary: summary?.summary,
      key_findings: summary?.key_findings,
    }),
  });
}

export async function getArchivedPapers(limit = 50, offset = 0, status?: string): Promise<{ papers: ArchivedPaper[]; total: number }> {
  const statusParam = status ? `&status=${status}` : '';
  return fetchAPI(`/archive/papers?limit=${limit}&offset=${offset}${statusParam}`);
}

export async function getArchivedPaper(paperId: number): Promise<ArchivedPaper> {
  return fetchAPI(`/archive/papers/${paperId}`);
}

export async function updateArchivedPaper(paperId: number, updates: {
  user_notes?: string;
  user_rating?: number;
  read_status?: string;
  linked_topic_ids?: string[];
}): Promise<void> {
  await fetchAPI(`/archive/papers/${paperId}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

export async function deleteArchivedPaper(paperId: number): Promise<void> {
  await fetchAPI(`/archive/papers/${paperId}`, { method: 'DELETE' });
}

// -----------------------------------------------------------------------------
// PDF Management
// -----------------------------------------------------------------------------

export async function uploadPdfToPaper(paperId: number, file: File): Promise<{ pdf_id: number }> {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await fetch(`${API_BASE}/archive/papers/${paperId}/upload-pdf`, {
    method: 'POST',
    body: formData,
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(error.detail);
  }
  
  return response.json();
}

export async function downloadPdfFromUrl(paperId: number): Promise<{ message: string; pdf_id?: number }> {
  return fetchAPI(`/archive/papers/${paperId}/download-pdf`, { method: 'POST' });
}

export function getPaperPdfUrl(paperId: number): string {
  return `${API_BASE}/archive/papers/${paperId}/pdf`;
}

export async function uploadStandalonePdf(file: File, title?: string): Promise<{ paper_id: number; title: string }> {
  const formData = new FormData();
  formData.append('file', file);
  if (title) {
    formData.append('title', title);
  }
  
  const response = await fetch(`${API_BASE}/papers/upload`, {
    method: 'POST',
    body: formData,
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(error.detail);
  }
  
  return response.json();
}

// -----------------------------------------------------------------------------
// Topic Archive
// -----------------------------------------------------------------------------

export async function archiveTopicReview(topic: Topic, review: TopicReview, userNotes?: string, confidenceLevel?: number): Promise<{ id: number }> {
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
      user_notes: userNotes,
      confidence_level: confidenceLevel,
    }),
  });
}

export async function getArchivedTopics(limit = 50, offset = 0, courseId?: string): Promise<{ topics: ArchivedTopic[]; total: number }> {
  const courseParam = courseId ? `&course_id=${courseId}` : '';
  return fetchAPI(`/archive/topics?limit=${limit}&offset=${offset}${courseParam}`);
}

export async function updateArchivedTopic(topicDbId: number, updates: {
  user_notes?: string;
  confidence_level?: number;
  linked_paper_ids?: number[];
}): Promise<void> {
  await fetchAPI(`/archive/topics/${topicDbId}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

export async function deleteArchivedTopic(topicDbId: number): Promise<void> {
  await fetchAPI(`/archive/topics/${topicDbId}`, { method: 'DELETE' });
}

// -----------------------------------------------------------------------------
// Quiz Archive
// -----------------------------------------------------------------------------

export async function archiveQuiz(
  topics: string[],
  questions: QuizQuestion[],
  results: Record<string, { correct: boolean; feedback: string }>,
  totalPoints: number,
  durationSeconds?: number
): Promise<{ id: number }> {
  const answeredQuestions = questions.map(q => ({
    ...q,
    result: results[q.id] || null,
  }));
  
  const correctCount = Object.values(results).filter(r => r.correct).length;
  const scoreEarned = correctCount * 2; // Assuming 2 points per correct
  const percentage = totalPoints > 0 ? (scoreEarned / totalPoints) * 100 : 0;
  
  return fetchAPI('/archive/quizzes', {
    method: 'POST',
    body: JSON.stringify({
      topics,
      topic_ids: questions.map(q => q.topic_id),
      total_questions: questions.length,
      total_points: totalPoints,
      score_earned: scoreEarned,
      percentage,
      questions: answeredQuestions,
      duration_seconds: durationSeconds,
    }),
  });
}

export async function getArchivedQuizzes(limit = 50, offset = 0): Promise<{ quizzes: ArchivedQuiz[]; total: number }> {
  return fetchAPI(`/archive/quizzes?limit=${limit}&offset=${offset}`);
}

export async function deleteArchivedQuiz(quizId: number): Promise<void> {
  await fetchAPI(`/archive/quizzes/${quizId}`, { method: 'DELETE' });
}

// -----------------------------------------------------------------------------
// Archive Stats
// -----------------------------------------------------------------------------

export async function getArchiveStats(): Promise<{
  papers: { total: number; completed: number };
  topics: { unique_topics: number; total_reviews: number };
  quizzes: { total: number; average_score: number };
}> {
  return fetchAPI('/archive/stats');
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

export async function regenerateQuiz(count = 5, difficulty = 'medium'): Promise<{
  topics: string[];
  questions: QuizQuestion[];
  total_points: number;
}> {
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
