/**
 * API Client for Daily Scholar Backend
 * Full paper lifecycle with seen tracking, PDF upload, archives,
 * and topic completion/rotation.
 */

// exported so other modules (e.g., layout's external API Docs link) point at
// the same backend URL without re-implementing the fallback. NEXT_PUBLIC_API_URL
// is inlined at build time; the localhost fallback is for local dev only.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Thrown by fetchAPI on a 401 response. Distinct subclass so the AuthBoundary
 * component can listen for the global 'daily-scholar:auth-error' event without
 * mistaking ordinary error toasts for authentication failures.
 *
 * In solo mode this should never fire — get_current_user_id falls back to the
 * '__local__' sentinel. It only triggers once CF_ACCESS_VERIFY_JWT is on and
 * the request arrives without a valid JWT (e.g., the user's CF session expired).
 */
export class AuthError extends Error {
  status: number;
  constructor(message = 'Authentication required') {
    super(message);
    this.name = 'AuthError';
    this.status = 401;
  }
}

// browser-only: dispatched on every 401 so AuthBoundary can show a banner
// from anywhere in the tree without prop-drilling. SSR guards are required
// because Next renders this file on the server first.
const AUTH_EVENT = 'daily-scholar:auth-error';

function emitAuthError(detail: { status: number; message: string; redirect?: string }) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(AUTH_EVENT, { detail }));
}

export const AUTH_ERROR_EVENT = AUTH_EVENT;

// fired after a successful login or logout so any useAuth() instance —
// even one mounted in the persistent layout above the page tree — can
// re-fetch /auth/me and update its UI. Without this, the layout-level
// UserMenu shows its boot-time "logged out" state forever.
const AUTH_CHANGED = 'daily-scholar:auth-changed';

function emitAuthChanged() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(AUTH_CHANGED));
}

export const AUTH_CHANGED_EVENT = AUTH_CHANGED;

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
  stream: string;
  active: boolean;
  weight: number;
  keywords: string[];
  arxiv_categories: string[];
  recency_days: number;
  min_relevance: number;
  key_concepts: string[];
  learning_objectives: string[];
  resources: string[];
  quiz_difficulty: string;
  prerequisites: string[];
  created_via: string;
  source_yaml_present: boolean;
  // Phase C ownership fields:
  //   owner_user_id === null  → system topic (visible to all, admin-only edit)
  //   owner_user_id === number → owned by users.id
  owner_user_id: number | null;
  visibility: 'private' | 'public';
  // Phase D: true when the caller has subscribed to this topic (only
  // populated on list endpoints; single-row GET returns false).
  is_subscribed: boolean;
  created_at: string;
  updated_at: string;

  // legacy fields kept for back-compat with /topics/{id}/review payloads;
  // backend's _topic_to_dict() populates course_id with the stream slug.
  course_id?: string;
  course_name?: string;
  week_covered?: number;
}

export interface TopicCreate {
  /** Admin-only override; server auto-generates for regular users. */
  id?: string;
  name: string;
  stream?: string;
  active?: boolean;
  weight?: number;
  keywords?: string[];
  arxiv_categories?: string[];
  recency_days?: number;
  min_relevance?: number;
  key_concepts?: string[];
  learning_objectives?: string[];
  resources?: string[];
  quiz_difficulty?: string;
  prerequisites?: string[];
  /** Admin-only override; defaults to caller's id (or null for admins). */
  owner_user_id?: number | null;
  /** private (default for user topics) | public (default for system). */
  visibility?: 'private' | 'public';
}

export type TopicUpdate = Partial<Omit<TopicCreate, 'id'>>;

export type ScopeMode = 'silo' | 'multi' | 'all';

export interface Scope {
  user_id: string;
  scope_mode: ScopeMode;
  scope_topic_ids: string[];
  updated_at: string;
}

export interface TopicReview {
  review_content: string;
  key_points: string[];
  connections: string[];
  practice_suggestions: string[];
}

export type TopicStatus = 'active' | 'completed' | 'review_later';

export interface ArchivedTopic {
  id: number;
  topic_id: string;
  topic_name: string;
  course_id: string;
  course_name: string;
  week_covered: number;
  review_count: number;
  confidence_level?: number;
  user_notes?: string;
  status: TopicStatus;
  completed_at?: string;
  linked_paper_ids?: number[];
  last_reviewed_at: string;
  key_points?: string[];
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
  duration_seconds?: number;
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
    topics_completed: number;
    topics_review_later: number;
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

export interface TopicStatusSummary {
  total_topics: number;
  active: number;
  review_later: number;
  completed: number;
  completion_percentage: number;
}

// =============================================================================
// API FUNCTIONS
// =============================================================================

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    // include cookies cross-origin so Cloudflare Access (gating the API
    // hostname) receives its session cookie set on the .daily-scholar.com
    // parent domain. Without this the browser drops the cookie and Access
    // 302s every request to its login page, which CORS then blocks.
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    // 401 gets its own subclass + a global event so the AuthBoundary can
    // redirect to /login from anywhere in the tree.
    if (response.status === 401) {
      const message = error.detail || 'Authentication required';
      emitAuthError({ status: 401, message });
      throw new AuthError(message);
    }
    // 403 with one of the auth-status reasons routes to the matching
    // placeholder page. Same event channel, different status, so the
    // AuthBoundary can branch on it.
    if (response.status === 403) {
      const detail = String(error.detail || '');
      if (/pending approval/i.test(detail)) {
        emitAuthError({ status: 403, message: detail, redirect: '/account/pending' });
      } else if (/suspended/i.test(detail)) {
        emitAuthError({ status: 403, message: detail, redirect: '/account/suspended' });
      }
    }
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
    credentials: 'include',
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
    credentials: 'include',
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

export async function archiveTopicReview(
  topic: Topic,
  review: TopicReview,
  userNotes?: string,
  confidenceLevel?: number,
  status?: TopicStatus,
): Promise<{ id: number }> {
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
      status: status || 'active',
    }),
  });
}

export async function getArchivedTopics(
  limit = 50, offset = 0, courseId?: string, status?: TopicStatus,
): Promise<{ topics: ArchivedTopic[]; total: number }> {
  let params = `limit=${limit}&offset=${offset}`;
  if (courseId) params += `&course_id=${courseId}`;
  if (status) params += `&status=${status}`;
  return fetchAPI(`/archive/topics?${params}`);
}

export async function updateArchivedTopic(topicDbId: number, updates: {
  user_notes?: string;
  confidence_level?: number;
  linked_paper_ids?: number[];
  status?: TopicStatus;
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
// Topic Status & Rotation (New)
// -----------------------------------------------------------------------------

export async function setTopicStatus(topicId: string, status: TopicStatus): Promise<{ message: string; id: number }> {
  return fetchAPI(`/topics/${topicId}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status }),
  });
}

export async function getRandomTopicReview(excludeTopicIds?: string[]): Promise<{
  topic_reviews: Array<{ topic: Topic; review: TopicReview }>;
}> {
  const excludeParam = excludeTopicIds?.length ? `?exclude=${excludeTopicIds.join(',')}` : '';
  return fetchAPI(`/topics/random-review${excludeParam}`);
}

export async function getTopicStatusSummary(): Promise<TopicStatusSummary> {
  return fetchAPI('/topics/status-summary');
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
  topics: { unique_topics: number; total_reviews: number; completed: number };
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

/** Partial-refresh selectors for getDailyContent(). */
export type DailyRefresh = '' | 'paper' | 'review' | 'all';

export async function getDailyContent(refresh: DailyRefresh | boolean = ''): Promise<DailyContent & { cached?: boolean }> {
  // legacy callers may pass `true` meaning "refresh all"
  const value: DailyRefresh = refresh === true ? 'all' : refresh === false ? '' : refresh;
  return fetchAPI(`/daily${value ? `?refresh=${value}` : ''}`);
}

// -----------------------------------------------------------------------------
// Topic catalog (unified Topic model, replaces interests + courses)
// -----------------------------------------------------------------------------

export async function listTopics(opts?: {
  stream?: string;
  active?: boolean;
  includeOrphaned?: boolean;
}): Promise<Topic[]> {
  const params = new URLSearchParams();
  if (opts?.stream) params.set('stream', opts.stream);
  if (opts?.active !== undefined) params.set('active', String(opts.active));
  if (opts?.includeOrphaned !== undefined) params.set('include_orphaned', String(opts.includeOrphaned));
  const qs = params.toString();
  return fetchAPI(`/topics${qs ? `?${qs}` : ''}`);
}

export async function listStreams(): Promise<{ streams: string[] }> {
  return fetchAPI('/topics/streams');
}

export async function getTopic(id: string): Promise<Topic> {
  return fetchAPI(`/topics/${encodeURIComponent(id)}`);
}

export async function createTopic(payload: TopicCreate): Promise<Topic> {
  return fetchAPI('/topics', { method: 'POST', body: JSON.stringify(payload) });
}

export async function updateTopic(id: string, payload: TopicUpdate): Promise<Topic> {
  return fetchAPI(`/topics/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function deleteTopic(id: string, opts?: { hard?: boolean }): Promise<{ deleted: string; mode: string }> {
  const qs = opts?.hard ? '?hard=true' : '';
  return fetchAPI(`/topics/${encodeURIComponent(id)}${qs}`, { method: 'DELETE' });
}

export async function importTopicsFromYaml(): Promise<{ upserted: number; inserted: number; updated: number; marked_orphaned: number }> {
  return fetchAPI('/topics/import-yaml', { method: 'POST' });
}

export async function exportTopicsToYaml(): Promise<{ exported: number; directory: string }> {
  return fetchAPI('/topics/export-yaml', { method: 'POST' });
}

// -----------------------------------------------------------------------------
// Topic discovery + subscriptions (Phase D)
// -----------------------------------------------------------------------------

export async function searchTopics(q: string, limit = 50): Promise<Topic[]> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  return fetchAPI(`/topics/search?${params.toString()}`);
}

export async function subscribeTopic(
  topicId: string,
): Promise<{ ok: boolean; topic_id: string; subscribed_at: string }> {
  return fetchAPI(`/topics/${encodeURIComponent(topicId)}/subscribe`, { method: 'POST' });
}

export async function unsubscribeTopic(
  topicId: string,
): Promise<{ ok: boolean; removed: boolean }> {
  return fetchAPI(`/topics/${encodeURIComponent(topicId)}/subscribe`, { method: 'DELETE' });
}

// -----------------------------------------------------------------------------
// Onboarding wizard (Phase E)
// -----------------------------------------------------------------------------

export interface TopicDraft {
  name: string;
  keywords: string[];
  arxiv_categories: string[];
  key_concepts: string[];
}

export async function generateTopicDraft(interests: string): Promise<TopicDraft> {
  return fetchAPI('/onboarding/generate-topic', {
    method: 'POST',
    body: JSON.stringify({ interests }),
  });
}

export async function completeOnboarding(
  draft: TopicDraft & { visibility?: 'private' | 'public' },
): Promise<{ ok: boolean; topic_id: string; name: string; onboarded: boolean }> {
  return fetchAPI('/onboarding/complete', {
    method: 'POST',
    body: JSON.stringify(draft),
  });
}

export async function skipOnboarding(): Promise<{ ok: boolean; onboarded: boolean }> {
  return fetchAPI('/onboarding/skip', { method: 'POST' });
}

// -----------------------------------------------------------------------------
// Scope (silo / multi / all topic selector)
// -----------------------------------------------------------------------------

export async function getScope(): Promise<Scope> {
  return fetchAPI('/user/scope');
}

export async function updateScope(payload: { scope_mode: ScopeMode; scope_topic_ids: string[] }): Promise<Scope> {
  return fetchAPI('/user/scope', { method: 'PUT', body: JSON.stringify(payload) });
}

// -----------------------------------------------------------------------------
// Scheduled notifications (cron-scheduled push)
// -----------------------------------------------------------------------------

export interface NotificationTypeMeta {
  key: string;
  label: string;
  description: string;
  default_cron: string;
}

export interface NotificationTypeEntry {
  enabled: boolean;
  cron: string;
}

export interface NotificationSettings {
  timezone: string;
  types: Record<string, NotificationTypeEntry>;
}

export interface NotificationPayloadPreview {
  type: string;
  payload: Record<string, unknown> | null;
  would_send: boolean;
}

export interface NotificationDispatchResult {
  ok: boolean;
  type?: string;
  payload?: Record<string, unknown>;
  result?: { sent?: number; removed?: number; failed?: number };
  skipped?: string;
  error?: string;
}

export interface NotificationJob {
  type: string;
  id: string;
  trigger: string;
  next_run_time: string | null;
}

export async function listNotificationTypes(): Promise<{ types: NotificationTypeMeta[] }> {
  return fetchAPI('/notifications/types');
}

export async function getNotificationSettings(): Promise<NotificationSettings> {
  return fetchAPI('/notifications/settings');
}

export async function updateNotificationSettings(
  settings: NotificationSettings,
): Promise<{ settings: NotificationSettings; scheduler: Record<string, number> }> {
  return fetchAPI('/notifications/settings', {
    method: 'PUT',
    body: JSON.stringify(settings),
  });
}

export async function previewNotification(typeKey: string): Promise<NotificationPayloadPreview> {
  return fetchAPI(`/notifications/preview/${encodeURIComponent(typeKey)}`);
}

export async function testNotification(typeKey: string): Promise<NotificationDispatchResult> {
  return fetchAPI(`/notifications/test/${encodeURIComponent(typeKey)}`, { method: 'POST' });
}

export async function listNotificationJobs(): Promise<{
  scheduler_running: boolean;
  jobs: NotificationJob[];
}> {
  return fetchAPI('/notifications/jobs');
}

// -----------------------------------------------------------------------------
// In-app auth (Phase A)
// -----------------------------------------------------------------------------

export type UserStatus = 'pending' | 'active' | 'suspended';
export type UserRole = 'user' | 'admin';

export interface AuthUser {
  email: string;
  user_id: string;
  role: UserRole;
  status: UserStatus;
  /** Phase E: false until the wizard runs (or is skipped). */
  onboarded: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface SignupBody {
  email: string;
  password: string;
  /** Optional custom handle. Omit to default to the email. */
  user_id?: string;
  /** Required unless the server is running with OPEN_SIGNUP=1 (local dev). */
  invite_code?: string;
}

export interface LoginBody {
  email: string;
  password: string;
}

export async function signup(body: SignupBody): Promise<{ profile: AuthUser; message: string }> {
  return fetchAPI('/auth/signup', { method: 'POST', body: JSON.stringify(body) });
}

export async function login(body: LoginBody): Promise<{ profile: AuthUser; pending: boolean }> {
  const result = await fetchAPI<{ profile: AuthUser; pending: boolean }>(
    '/auth/login',
    { method: 'POST', body: JSON.stringify(body) },
  );
  // notify other useAuth() instances (e.g., the layout's UserMenu) so they
  // re-fetch /auth/me and reflect the new logged-in state
  emitAuthChanged();
  return result;
}

export async function logout(): Promise<{ ok: boolean; revoked: boolean }> {
  const result = await fetchAPI<{ ok: boolean; revoked: boolean }>(
    '/auth/logout',
    { method: 'POST' },
  );
  emitAuthChanged();
  return result;
}

export async function getMe(): Promise<{ profile: AuthUser }> {
  return fetchAPI('/auth/me');
}

// -----------------------------------------------------------------------------
// Admin: invite codes (Phase B)
// -----------------------------------------------------------------------------

export type InviteState = 'available' | 'exhausted' | 'expired' | 'revoked';

export interface InviteSummary {
  id: number;
  code: string;
  created_at: string;
  expires_at: string | null;
  max_uses: number;
  uses: number;
  redeemed_at: string | null;
  revoked_at: string | null;
  state: InviteState;
}

export interface CreateInviteBody {
  /** 1-365 days from now; omit for a non-expiring code. */
  expires_in_days?: number;
  /** Default 1 (single-use). */
  max_uses?: number;
}

export async function listInvites(includeRevoked = true): Promise<{ invites: InviteSummary[] }> {
  const qs = includeRevoked ? '' : '?include_revoked=false';
  return fetchAPI(`/admin/invites${qs}`);
}

export async function createInvite(body: CreateInviteBody): Promise<{ invite: InviteSummary }> {
  return fetchAPI('/admin/invites', { method: 'POST', body: JSON.stringify(body) });
}

export async function revokeInvite(id: number): Promise<{ ok: boolean; revoked: boolean }> {
  return fetchAPI(`/admin/invites/${id}`, { method: 'DELETE' });
}

// -----------------------------------------------------------------------------
// Admin: approval queue (Phase B)
// -----------------------------------------------------------------------------

export interface PendingUserSummary {
  id: number;
  email: string;
  user_id: string;
  created_at: string;
  waiting_seconds: number;
}

export async function listPendingApprovals(): Promise<{ pending: PendingUserSummary[]; count: number }> {
  return fetchAPI('/admin/approvals');
}

export async function approveUser(pendingUserId: number): Promise<{
  ok: boolean; user_id?: string; email?: string; approved_at?: string; message?: string;
}> {
  return fetchAPI(`/admin/approvals/${pendingUserId}/approve`, { method: 'POST' });
}

export async function rejectUser(pendingUserId: number): Promise<{ ok: boolean; deleted_user_id?: string }> {
  return fetchAPI(`/admin/approvals/${pendingUserId}/reject`, { method: 'POST' });
}
