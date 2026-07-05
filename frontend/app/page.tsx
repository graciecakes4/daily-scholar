'use client';

import { useState, useEffect } from 'react';
import {
  getDailyContent, checkHealth, regenerateQuiz, getUserStats,
  archivePaper, archiveTopicReview, archiveQuiz, submitAnswer,
  type DailyContent, type QuizQuestion, type UserStats
} from '@/lib/api';

// Icons
const BookIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
  </svg>
);

const BrainIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
  </svg>
);

const QuizIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
  </svg>
);

const ArchiveIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
  </svg>
);

const FireIcon = ({ className = 'w-5 h-5' }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
  </svg>
);

const CheckIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const XIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const ExternalLinkIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
  </svg>
);

export default function DashboardPage() {
  const [dailyContent, setDailyContent] = useState<DailyContent | null>(null);
  const [userStats, setUserStats] = useState<UserStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<'paper' | 'review' | 'quiz'>('review');
  const [quizAnswers, setQuizAnswers] = useState<Record<string, string>>({});
  const [quizResults, setQuizResults] = useState<Record<string, { correct: boolean; feedback: string }>>({});
  const [apiStatus, setApiStatus] = useState<'checking' | 'connected' | 'error'>('checking');
  const [regeneratingQuiz, setRegeneratingQuiz] = useState(false);
  const [quizQuestions, setQuizQuestions] = useState<QuizQuestion[]>([]);
  const [quizTotalPoints, setQuizTotalPoints] = useState(0);
  
  // Archive states
  const [archivingPaper, setArchivingPaper] = useState(false);
  const [paperArchived, setPaperArchived] = useState(false);
  const [archivingTopic, setArchivingTopic] = useState<string | null>(null);
  const [archivedTopics, setArchivedTopics] = useState<Set<string>>(new Set());
  const [archivingQuiz, setArchivingQuiz] = useState(false);
  const [quizArchived, setQuizArchived] = useState(false);

  useEffect(() => {
    async function loadContent() {
      try {
        await checkHealth();
        setApiStatus('connected');
        
        const [content, stats] = await Promise.all([
          getDailyContent(),
          getUserStats().catch(() => null),
        ]);
        
        setDailyContent(content);
        setUserStats(stats);
        setQuizQuestions(content.quiz.questions);
        setQuizTotalPoints(content.quiz.total_points);
        
        if (content.paper) {
          setActiveSection('paper');
        } else if (content.topic_reviews.length > 0) {
          setActiveSection('review');
        }
      } catch (err) {
        setApiStatus('error');
        setError(err instanceof Error ? err.message : 'Failed to load content');
      } finally {
        setLoading(false);
      }
    }
    loadContent();
  }, []);

  const handleArchivePaper = async () => {
    if (!dailyContent?.paper || !dailyContent?.paper_summary) return;
    setArchivingPaper(true);
    try {
      await archivePaper(dailyContent.paper, dailyContent.paper_summary);
      setPaperArchived(true);
    } catch (err) {
      console.error('Failed to archive paper:', err);
    } finally {
      setArchivingPaper(false);
    }
  };

  const [refreshingPaper, setRefreshingPaper] = useState(false);
  const handleNewPaper = async () => {
    setRefreshingPaper(true);
    setPaperArchived(false);
    try {
      const content = await getDailyContent('paper');
      setDailyContent(content);
      // paper-only refresh leaves the quiz alone, but rehydrate state for safety
      setQuizQuestions(content.quiz.questions);
      setQuizTotalPoints(content.quiz.total_points);
    } catch (err) {
      console.error('Failed to refresh paper:', err);
    } finally {
      setRefreshingPaper(false);
    }
  };

  const [refreshingReview, setRefreshingReview] = useState(false);
  const handleNewReview = async () => {
    setRefreshingReview(true);
    setArchivedTopics(new Set());
    setQuizArchived(false);
    setQuizAnswers({});
    setQuizResults({});
    try {
      const content = await getDailyContent('review');
      setDailyContent(content);
      setQuizQuestions(content.quiz.questions);
      setQuizTotalPoints(content.quiz.total_points);
    } catch (err) {
      console.error('Failed to refresh topic review:', err);
    } finally {
      setRefreshingReview(false);
    }
  };

  const handleArchiveTopic = async (index: number) => {
    const topicReview = dailyContent?.topic_reviews[index];
    if (!topicReview) return;
    
    const topicId = topicReview.topic.id;
    setArchivingTopic(topicId);
    try {
      await archiveTopicReview(topicReview.topic, topicReview.review);
      setArchivedTopics(prev => new Set(prev).add(topicId));
    } catch (err) {
      console.error('Failed to archive topic:', err);
    } finally {
      setArchivingTopic(null);
    }
  };

  const handleArchiveQuiz = async () => {
    if (quizQuestions.length === 0 || Object.keys(quizResults).length === 0) return;
    setArchivingQuiz(true);
    try {
      const topics = [...new Set(quizQuestions.map(q => q.topic_name || 'Unknown'))];
      await archiveQuiz(topics, quizQuestions, quizResults, quizTotalPoints);
      setQuizArchived(true);
    } catch (err) {
      console.error('Failed to archive quiz:', err);
    } finally {
      setArchivingQuiz(false);
    }
  };

  const handleAnswerChange = (questionId: string, answer: string) => {
    setQuizAnswers(prev => ({ ...prev, [questionId]: answer }));
  };

  const handleSubmitAnswer = async (questionId: string) => {
    const answer = quizAnswers[questionId];
    if (!answer) return;
    try {
      // use the shared client so we get API_BASE + credentials: 'include' +
      // 401 handling — the previous hardcoded fetch broke in prod because it
      // pointed at localhost and skipped the CF Access cookie.
      const result = await submitAnswer(questionId, answer);
      setQuizResults(prev => ({
        ...prev,
        [questionId]: { correct: result.is_correct, feedback: result.feedback }
      }));
    } catch (err) {
      console.error('Failed to submit answer:', err);
    }
  };

  const handleRegenerateQuiz = async () => {
    setRegeneratingQuiz(true);
    setQuizArchived(false);
    try {
      const newQuiz = await regenerateQuiz(5, 'medium');
      setQuizQuestions(newQuiz.questions);
      setQuizTotalPoints(newQuiz.total_points);
      setQuizAnswers({});
      setQuizResults({});
    } catch (err) {
      console.error('Failed to regenerate quiz:', err);
    } finally {
      setRegeneratingQuiz(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-gold to-gold-dark animate-pulse" />
          <p className="text-ink-2">Loading your daily learning content...</p>
        </div>
      </div>
    );
  }

  if (apiStatus === 'error') {
    return (
      <div className="max-w-2xl mx-auto mt-12">
        <div className="bg-rust/5 border border-rust/25 rounded-2xl p-8 text-center">
          <h2 className="text-xl font-semibold text-rust mb-2">Cannot Connect to Backend</h2>
          <p className="text-rust mb-4">{error}</p>
          <code className="bg-rust/10 px-3 py-1 rounded text-sm">uvicorn backend.main:app --reload</code>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Stats Bar — "numbered cards" editorial treatment (see
          mockups/stats_bar_option2_numbered_cards.html for the source design
          and the two sibling alternatives it was chosen over). 2x2 grid on
          mobile, single row on md+ to keep four stats on screen without
          overflowing narrow viewports.

          TODO(design): mockups/stats_bar_option3_observatory.html (dark,
          amber-glow "night observatory" palette) was explored alongside this
          and liked enough to revisit — turn it into a user-selectable
          alternate visual palette (a "theme" preference on the account, not
          just for this bar) rather than a one-off swap. Needs a persisted
          preference (e.g. a users.theme column + a toggle in
          /settings/account) and this component reading that preference to
          pick a variant. Not built yet — shipping the editorial default now. */}
      {userStats && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="group relative overflow-hidden rounded bg-paper-2 border border-rule px-4 pt-4 pb-3.5 transition-all duration-200 ease-out hover:border-gold hover:-translate-y-px">
            <div className="absolute top-0 left-0 w-full h-[3px] bg-gradient-to-r from-rust to-gold" />
            <div className="flex items-center gap-1.5 font-serif italic text-[10px] font-medium uppercase tracking-[0.12em] text-gold-dark">
              <FireIcon className="w-3 h-3 text-rust" />
              I · Streak
            </div>
            <div className="font-serif font-medium text-[34px] leading-tight tracking-[-0.02em] text-ink mt-2 mb-0.5">
              {userStats.streaks.current}<span className="text-[15px] font-sans font-medium text-muted ml-1">days</span>
            </div>
            <div className="text-[11.5px] text-ink-2">
              best run <span className="text-gold-dark font-semibold">{userStats.streaks.longest} days</span>
            </div>
          </div>

          <div className="relative overflow-hidden rounded bg-paper-2 border border-rule px-4 pt-4 pb-3.5 transition-all duration-200 ease-out hover:border-gold hover:-translate-y-px">
            <div className="absolute top-0 left-0 w-full h-[3px] bg-rule" />
            <div className="font-serif italic text-[10px] font-medium uppercase tracking-[0.12em] text-muted">II · Read</div>
            <div className="font-serif font-medium text-[34px] leading-tight tracking-[-0.02em] text-ink mt-2 mb-0.5">
              {userStats.lifetime.papers_seen}
            </div>
            <div className="text-[11.5px] text-ink-2 truncate">papers seen to date</div>
          </div>

          <div className="relative overflow-hidden rounded bg-paper-2 border border-rule px-4 pt-4 pb-3.5 transition-all duration-200 ease-out hover:border-gold hover:-translate-y-px">
            <div className="absolute top-0 left-0 w-full h-[3px] bg-rule" />
            <div className="font-serif italic text-[10px] font-medium uppercase tracking-[0.12em] text-muted">III · Kept</div>
            <div className="font-serif font-medium text-[34px] leading-tight tracking-[-0.02em] text-ink mt-2 mb-0.5">
              {userStats.lifetime.papers_archived}
            </div>
            <div className="text-[11.5px] text-ink-2 truncate">archived for later</div>
          </div>

          <div className="relative overflow-hidden rounded bg-paper-2 border border-rule px-4 pt-4 pb-3.5 transition-all duration-200 ease-out hover:border-gold hover:-translate-y-px">
            <div className="absolute top-0 left-0 w-full h-[3px] bg-rule" />
            <div className="font-serif italic text-[10px] font-medium uppercase tracking-[0.12em] text-muted">IV · Accuracy</div>
            <div className="font-serif font-medium text-[34px] leading-tight tracking-[-0.02em] text-ink mt-2 mb-0.5">
              {userStats.lifetime.quiz_accuracy}<span className="text-[15px] font-sans font-medium text-muted ml-1">%</span>
            </div>
            <div className="text-[11.5px] text-ink-2 truncate">across recent quizzes</div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-ink">Daily Scholar</h1>
          <p className="text-ink-2 mt-1">{dailyContent?.date}</p>
        </div>
      </div>

      {/* Section Navigation — equal 3-col grid on mobile so the buttons share
          width and never overflow; flex with natural widths on md+. Labels are
          abbreviated on mobile ("Paper" instead of "Today's Paper") */}
      <div className="grid grid-cols-3 gap-1 md:flex md:gap-2 border-b border-rule pb-2">
        <button
          data-tour="paper"
          onClick={() => setActiveSection('paper')}
          className={`flex items-center justify-center gap-1.5 px-2 py-2 md:px-4 rounded-lg font-medium text-sm md:text-base transition-all min-w-0 ${
            activeSection === 'paper' ? 'bg-gold/10 text-gold-dark' : 'text-ink-2 hover:bg-paper-3'
          }`}
        >
          <BookIcon />
          <span className="truncate"><span className="hidden md:inline">Today's </span>Paper</span>
          {dailyContent?.paper && <span className="w-2 h-2 rounded-full bg-gold flex-shrink-0" />}
        </button>
        <button
          data-tour="review"
          onClick={() => setActiveSection('review')}
          className={`flex items-center justify-center gap-1.5 px-2 py-2 md:px-4 rounded-lg font-medium text-sm md:text-base transition-all min-w-0 ${
            activeSection === 'review' ? 'bg-moss/10 text-moss' : 'text-ink-2 hover:bg-paper-3'
          }`}
        >
          <BrainIcon />
          <span className="truncate"><span className="hidden md:inline">Topic </span>Review</span>
          {dailyContent?.topic_reviews && (
            <span className="px-2 py-0.5 bg-moss/20 text-moss text-xs rounded-full flex-shrink-0">
              {dailyContent.topic_reviews.length}
            </span>
          )}
        </button>
        <button
          data-tour="quiz"
          onClick={() => setActiveSection('quiz')}
          className={`flex items-center justify-center gap-1.5 px-2 py-2 md:px-4 rounded-lg font-medium text-sm md:text-base transition-all min-w-0 ${
            activeSection === 'quiz' ? 'bg-gold/10 text-gold-dark' : 'text-ink-2 hover:bg-paper-3'
          }`}
        >
          <QuizIcon />
          <span className="truncate">Quiz</span>
          <span className="px-2 py-0.5 bg-gold/20 text-gold-dark text-xs rounded-full flex-shrink-0">
            {quizQuestions.length}
          </span>
        </button>
      </div>

      {/* Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          
          {/* Paper Section */}
          {activeSection === 'paper' && (
            <div className="bg-paper-2 rounded-2xl border border-rule overflow-hidden">
              {dailyContent?.paper ? (
                <>
                  <div className="p-6">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="px-2 py-1 bg-gold/10 text-gold-dark text-xs font-medium rounded">
                        {dailyContent.paper.source}
                      </span>
                      {dailyContent.paper.primary_category && (
                        <span className="px-2 py-1 bg-paper-3 text-ink-2 text-xs rounded">
                          {dailyContent.paper.primary_category}
                        </span>
                      )}
                    </div>
                    <h2 className="text-xl font-bold text-ink mb-2">{dailyContent.paper.title}</h2>
                    <p className="text-sm text-ink-2 mb-4">
                      {dailyContent.paper.authors?.slice(0, 4).join(', ')}
                      {dailyContent.paper.authors?.length > 4 && ' et al.'}
                    </p>

                    {dailyContent.paper_summary && (
                      <div className="space-y-4">
                        <div className="bg-gold/5 rounded-xl p-4">
                          <h3 className="font-semibold text-gold-dark mb-2">Summary</h3>
                          <p className="text-gold-dark text-sm">{dailyContent.paper_summary.summary}</p>
                        </div>
                        {dailyContent.paper_summary.key_findings?.length > 0 && (
                          <div>
                            <h3 className="font-semibold text-ink mb-2">Key Findings</h3>
                            <ul className="space-y-1">
                              {dailyContent.paper_summary.key_findings.map((f, i) => (
                                <li key={i} className="text-sm text-ink-2 flex items-start gap-2">
                                  <span className="text-gold-dark">•</span>{f}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="border-t border-rule p-4 bg-paper flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                    <div className="flex gap-2">
                      <a href={dailyContent.paper.url} target="_blank" rel="noopener noreferrer"
                         className="flex items-center gap-2 px-4 py-2 bg-paper-2 border border-rule rounded-lg text-sm hover:bg-paper">
                        <ExternalLinkIcon /> Open
                      </a>
                      {dailyContent.paper.pdf_url && (
                        <a href={dailyContent.paper.pdf_url} target="_blank" rel="noopener noreferrer"
                           className="px-4 py-2 bg-paper-2 border border-rule rounded-lg text-sm hover:bg-paper">
                          PDF
                        </a>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        onClick={handleNewPaper}
                        disabled={refreshingPaper}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-paper-2 border border-rule text-ink-2 hover:bg-paper disabled:opacity-50"
                        title="Skip this paper and find a different one"
                      >
                        {refreshingPaper ? (
                          <span className="w-4 h-4 border-2 border-muted border-t-transparent rounded-full animate-spin" />
                        ) : (
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                        )}
                        {refreshingPaper ? 'Loading…' : 'New paper'}
                      </button>
                      <button
                        onClick={handleArchivePaper}
                        disabled={archivingPaper || paperArchived}
                        className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium ${
                          paperArchived ? 'bg-moss/10 text-moss' : 'bg-gold-dark text-white hover:brightness-90'
                        } disabled:opacity-50`}
                      >
                        {archivingPaper ? (
                          <span className="w-4 h-4 border-2 border-paper-2 border-t-transparent rounded-full animate-spin" />
                        ) : paperArchived ? <CheckIcon /> : <ArchiveIcon />}
                        {paperArchived ? 'Saved!' : 'Save to Archive'}
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="p-12 text-center">
                  <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-paper-3 flex items-center justify-center">
                    <BookIcon />
                  </div>
                  <h3 className="text-lg font-semibold text-ink-2 mb-2">No New Papers Today</h3>
                  <p className="text-muted text-sm">Check back tomorrow for new papers!</p>
                </div>
              )}
            </div>
          )}

          {/* Topic Review Section */}
          {activeSection === 'review' && dailyContent?.topic_reviews?.map((tr, index) => (
            <div key={index} className="bg-paper-2 rounded-2xl border border-rule overflow-hidden">
              <div className="p-6">
                <div className="flex flex-col gap-3 mb-4 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <span className="px-2 py-1 bg-moss/10 text-moss text-xs font-medium rounded">
                      {tr.topic.course_name}
                    </span>
                    <h2 className="text-xl font-bold text-ink mt-2 break-words">{tr.topic.name}</h2>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {index === 0 && (
                      <button
                        onClick={handleNewReview}
                        disabled={refreshingReview}
                        className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm bg-paper-2 border border-rule text-ink-2 hover:bg-paper disabled:opacity-50"
                        title="Generate a different topic review"
                      >
                        {refreshingReview ? (
                          <span className="w-4 h-4 border-2 border-muted border-t-transparent rounded-full animate-spin" />
                        ) : (
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                        )}
                        {refreshingReview ? 'Loading…' : 'New'}
                      </button>
                    )}
                    <button
                      onClick={() => handleArchiveTopic(index)}
                      disabled={archivingTopic === tr.topic.id || archivedTopics.has(tr.topic.id)}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
                        archivedTopics.has(tr.topic.id) ? 'bg-moss/10 text-moss' : 'bg-paper-3 hover:bg-rule'
                      } disabled:opacity-50`}
                    >
                      {archivingTopic === tr.topic.id ? (
                        <span className="w-4 h-4 border-2 border-muted border-t-transparent rounded-full animate-spin" />
                      ) : archivedTopics.has(tr.topic.id) ? <><CheckIcon /> Saved</> : <><ArchiveIcon /> Save</>}
                    </button>
                  </div>
                </div>
                <p className="text-ink-2 mb-4">{tr.review.review_content}</p>
                <div className="grid md:grid-cols-2 gap-4">
                  {tr.review.key_points?.length > 0 && (
                    <div className="bg-moss/5 rounded-xl p-4">
                      <h4 className="font-semibold text-moss mb-2">Key Points</h4>
                      <ul className="space-y-1">
                        {tr.review.key_points.map((p, i) => (
                          <li key={i} className="text-sm text-moss">✓ {p}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {tr.review.practice_suggestions?.length > 0 && (
                    <div className="bg-gold/5 rounded-xl p-4">
                      <h4 className="font-semibold text-gold-dark mb-2">Practice Ideas</h4>
                      <ul className="space-y-1">
                        {tr.review.practice_suggestions.map((s, i) => (
                          <li key={i} className="text-sm text-gold-dark">→ {s}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}

          {/* Quiz Section */}
          {activeSection === 'quiz' && (
            <div className="bg-paper-2 rounded-2xl border border-rule overflow-hidden">
              <div className="p-4 border-b border-rule flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <h2 className="text-lg font-bold text-ink">Knowledge Check</h2>
                  <p className="text-sm text-muted">{quizQuestions.length} questions • {quizTotalPoints} points</p>
                </div>
                <div className="flex gap-2 flex-wrap">
                  {Object.keys(quizResults).length > 0 && !quizArchived && (
                    <button onClick={handleArchiveQuiz} disabled={archivingQuiz}
                            className="flex items-center gap-2 px-4 py-2 bg-moss text-white rounded-lg text-sm hover:brightness-90 disabled:opacity-50">
                      {archivingQuiz ? <span className="w-4 h-4 border-2 border-paper-2 border-t-transparent rounded-full animate-spin" /> : <ArchiveIcon />}
                      Save Results
                    </button>
                  )}
                  {quizArchived && (
                    <span className="flex items-center gap-2 px-4 py-2 bg-moss/10 text-moss rounded-lg text-sm">
                      <CheckIcon /> Saved!
                    </span>
                  )}
                  <button onClick={handleRegenerateQuiz} disabled={regeneratingQuiz}
                          className="flex items-center gap-2 px-4 py-2 bg-gold-dark text-white rounded-lg text-sm hover:brightness-90 disabled:opacity-50">
                    {regeneratingQuiz ? <span className="w-4 h-4 border-2 border-paper-2 border-t-transparent rounded-full animate-spin" /> : '🔄'}
                    New Quiz
                  </button>
                </div>
              </div>
              <div className="p-6 space-y-6">
                {quizQuestions.map((q, i) => (
                  <div key={q.id} className={`p-4 rounded-xl border ${
                    quizResults[q.id] ? (quizResults[q.id].correct ? 'bg-moss/5 border-moss/25' : 'bg-rust/5 border-rust/25') : 'bg-paper border-rule'
                  }`}>
                    <div className="flex items-start gap-3 mb-3">
                      <span className="w-8 h-8 rounded-full bg-gold/10 text-gold-dark font-bold flex items-center justify-center text-sm">{i + 1}</span>
                      <div>
                        <p className="font-medium text-ink">{q.question_text}</p>
                        {q.topic_name && <p className="text-xs text-muted mt-1">{q.topic_name}</p>}
                      </div>
                    </div>
                    {q.options && (
                      <div className="space-y-2 ml-11">
                        {q.options.map((opt, oi) => (
                          <label key={oi} className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer border ${
                            quizAnswers[q.id] === opt ? 'bg-gold/10 border-gold/30' : 'bg-paper-2 border-rule hover:bg-paper'
                          }`}>
                            <input type="radio" name={q.id} value={opt} checked={quizAnswers[q.id] === opt}
                                   onChange={() => handleAnswerChange(q.id, opt)} disabled={!!quizResults[q.id]} className="w-4 h-4 text-gold-dark" />
                            <span className="text-sm">{opt}</span>
                          </label>
                        ))}
                      </div>
                    )}
                    {!quizResults[q.id] && quizAnswers[q.id] && (
                      <div className="ml-11 mt-3">
                        <button onClick={() => handleSubmitAnswer(q.id)} className="px-4 py-2 bg-gold-dark text-white rounded-lg text-sm hover:brightness-90">
                          Check Answer
                        </button>
                      </div>
                    )}
                    {quizResults[q.id] && (
                      <div className={`ml-11 mt-3 p-3 rounded-lg ${quizResults[q.id].correct ? 'bg-moss/10' : 'bg-rust/10'}`}>
                        <div className="flex items-center gap-2 mb-1">
                          {quizResults[q.id].correct ? <CheckIcon /> : <XIcon />}
                          <span className={`font-medium ${quizResults[q.id].correct ? 'text-moss' : 'text-rust'}`}>
                            {quizResults[q.id].correct ? 'Correct!' : 'Not quite'}
                          </span>
                        </div>
                        <p className={`text-sm ${quizResults[q.id].correct ? 'text-moss' : 'text-rust'}`}>
                          {quizResults[q.id].feedback}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          <div className="bg-paper-2 rounded-2xl border border-rule p-6">
            <h3 className="font-bold text-ink mb-4">📚 Resources</h3>
            <div className="space-y-3">
              {dailyContent?.resources?.slice(0, 6).map((r, i) => (
                r.url ? (
                  <a key={i} href={r.url} target="_blank" rel="noopener noreferrer"
                     className="block p-3 rounded-lg border border-rule hover:border-gold/30 hover:bg-gold/5">
                    <p className="font-medium text-ink text-sm">{r.title}</p>
                    <p className="text-xs text-muted mt-1">{r.type}</p>
                  </a>
                ) : (
                  <div key={i} className="p-3 rounded-lg border border-rule">
                    <p className="font-medium text-ink text-sm">{r.title}</p>
                    <p className="text-xs text-muted mt-1">{r.type}</p>
                  </div>
                )
              ))}
            </div>
          </div>

          {userStats && (
            <div className="bg-gradient-to-br from-ink-2 to-ink rounded-2xl p-6 text-white">
              <h3 className="font-bold mb-4">Your Progress</h3>
              <div className="space-y-3 text-sm">
                <div className="flex justify-between"><span className="text-muted">Papers Read</span><span className="font-bold">{userStats.papers_by_status.completed}</span></div>
                <div className="flex justify-between"><span className="text-muted">Reading</span><span className="font-bold">{userStats.papers_by_status.reading}</span></div>
                <div className="flex justify-between"><span className="text-muted">Topics Reviewed</span><span className="font-bold">{userStats.lifetime.topics_reviewed}</span></div>
                <div className="flex justify-between"><span className="text-muted">Quizzes Taken</span><span className="font-bold">{userStats.lifetime.quizzes_taken}</span></div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
