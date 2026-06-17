'use client';

import { useState, useEffect } from 'react';
import { 
  getDailyContent, checkHealth, regenerateQuiz, getUserStats,
  archivePaper, archiveTopicReview, archiveQuiz,
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

const FireIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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
      const response = await fetch(
        `http://localhost:8000/quiz/answer?question_id=${questionId}&answer=${encodeURIComponent(answer)}`,
        { method: 'POST' }
      );
      const result = await response.json();
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
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 animate-pulse" />
          <p className="text-slate-600">Loading your daily learning content...</p>
        </div>
      </div>
    );
  }

  if (apiStatus === 'error') {
    return (
      <div className="max-w-2xl mx-auto mt-12">
        <div className="bg-red-50 border border-red-200 rounded-2xl p-8 text-center">
          <h2 className="text-xl font-semibold text-red-800 mb-2">Cannot Connect to Backend</h2>
          <p className="text-red-600 mb-4">{error}</p>
          <code className="bg-red-100 px-3 py-1 rounded text-sm">uvicorn backend.main:app --reload</code>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Stats Bar */}
      {userStats && (
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-4 text-white">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <FireIcon />
                <span className="font-bold text-lg">{userStats.streaks.current}</span>
                <span className="text-blue-100 text-sm">day streak</span>
              </div>
              <div className="text-blue-100 text-sm">
                <span className="text-white font-semibold">{userStats.lifetime.papers_seen}</span> papers seen
              </div>
              <div className="text-blue-100 text-sm">
                <span className="text-white font-semibold">{userStats.lifetime.papers_archived}</span> archived
              </div>
              <div className="text-blue-100 text-sm">
                <span className="text-white font-semibold">{userStats.lifetime.quiz_accuracy}%</span> quiz accuracy
              </div>
            </div>
            <div className="text-sm text-blue-100">
              Best: {userStats.streaks.longest} days
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Daily Scholar</h1>
          <p className="text-slate-600 mt-1">{dailyContent?.date}</p>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 border-b border-slate-200 pb-2">
        <button
          onClick={() => setActiveSection('paper')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all ${
            activeSection === 'paper' ? 'bg-blue-100 text-blue-700' : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <BookIcon />
          Today's Paper
          {dailyContent?.paper && <span className="w-2 h-2 rounded-full bg-blue-500" />}
        </button>
        <button
          onClick={() => setActiveSection('review')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all ${
            activeSection === 'review' ? 'bg-emerald-100 text-emerald-700' : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <BrainIcon />
          Topic Review
          {dailyContent?.topic_reviews && (
            <span className="px-2 py-0.5 bg-emerald-200 text-emerald-800 text-xs rounded-full">
              {dailyContent.topic_reviews.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveSection('quiz')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all ${
            activeSection === 'quiz' ? 'bg-purple-100 text-purple-700' : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <QuizIcon />
          Quiz
          <span className="px-2 py-0.5 bg-purple-200 text-purple-800 text-xs rounded-full">
            {quizQuestions.length}
          </span>
        </button>
      </div>

      {/* Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          
          {/* Paper Section */}
          {activeSection === 'paper' && (
            <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
              {dailyContent?.paper ? (
                <>
                  <div className="p-6">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded">
                        {dailyContent.paper.source}
                      </span>
                      {dailyContent.paper.primary_category && (
                        <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded">
                          {dailyContent.paper.primary_category}
                        </span>
                      )}
                    </div>
                    <h2 className="text-xl font-bold text-slate-900 mb-2">{dailyContent.paper.title}</h2>
                    <p className="text-sm text-slate-600 mb-4">
                      {dailyContent.paper.authors?.slice(0, 4).join(', ')}
                      {dailyContent.paper.authors?.length > 4 && ' et al.'}
                    </p>

                    {dailyContent.paper_summary && (
                      <div className="space-y-4">
                        <div className="bg-blue-50 rounded-xl p-4">
                          <h3 className="font-semibold text-blue-900 mb-2">Summary</h3>
                          <p className="text-blue-800 text-sm">{dailyContent.paper_summary.summary}</p>
                        </div>
                        {dailyContent.paper_summary.key_findings?.length > 0 && (
                          <div>
                            <h3 className="font-semibold text-slate-900 mb-2">Key Findings</h3>
                            <ul className="space-y-1">
                              {dailyContent.paper_summary.key_findings.map((f, i) => (
                                <li key={i} className="text-sm text-slate-700 flex items-start gap-2">
                                  <span className="text-blue-500">•</span>{f}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="border-t border-slate-100 p-4 bg-slate-50 flex items-center justify-between">
                    <div className="flex gap-2">
                      <a href={dailyContent.paper.url} target="_blank" rel="noopener noreferrer"
                         className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm hover:bg-slate-50">
                        <ExternalLinkIcon /> Open
                      </a>
                      {dailyContent.paper.pdf_url && (
                        <a href={dailyContent.paper.pdf_url} target="_blank" rel="noopener noreferrer"
                           className="px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm hover:bg-slate-50">
                          PDF
                        </a>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleNewPaper}
                        disabled={refreshingPaper}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                        title="Skip this paper and find a different one"
                      >
                        {refreshingPaper ? (
                          <span className="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
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
                          paperArchived ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-600 text-white hover:bg-blue-700'
                        } disabled:opacity-50`}
                      >
                        {archivingPaper ? (
                          <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        ) : paperArchived ? <CheckIcon /> : <ArchiveIcon />}
                        {paperArchived ? 'Saved!' : 'Save to Archive'}
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="p-12 text-center">
                  <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-slate-100 flex items-center justify-center">
                    <BookIcon />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-700 mb-2">No New Papers Today</h3>
                  <p className="text-slate-500 text-sm">Check back tomorrow for new papers!</p>
                </div>
              )}
            </div>
          )}

          {/* Topic Review Section */}
          {activeSection === 'review' && dailyContent?.topic_reviews?.map((tr, index) => (
            <div key={index} className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
              <div className="p-6">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <span className="px-2 py-1 bg-emerald-100 text-emerald-700 text-xs font-medium rounded">
                      {tr.topic.course_name}
                    </span>
                    <h2 className="text-xl font-bold text-slate-900 mt-2">{tr.topic.name}</h2>
                  </div>
                  <div className="flex items-center gap-2">
                    {index === 0 && (
                      <button
                        onClick={handleNewReview}
                        disabled={refreshingReview}
                        className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                        title="Generate a different topic review"
                      >
                        {refreshingReview ? (
                          <span className="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
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
                        archivedTopics.has(tr.topic.id) ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 hover:bg-slate-200'
                      } disabled:opacity-50`}
                    >
                      {archivingTopic === tr.topic.id ? (
                        <span className="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
                      ) : archivedTopics.has(tr.topic.id) ? <><CheckIcon /> Saved</> : <><ArchiveIcon /> Save</>}
                    </button>
                  </div>
                </div>
                <p className="text-slate-700 mb-4">{tr.review.review_content}</p>
                <div className="grid md:grid-cols-2 gap-4">
                  {tr.review.key_points?.length > 0 && (
                    <div className="bg-emerald-50 rounded-xl p-4">
                      <h4 className="font-semibold text-emerald-900 mb-2">Key Points</h4>
                      <ul className="space-y-1">
                        {tr.review.key_points.map((p, i) => (
                          <li key={i} className="text-sm text-emerald-800">✓ {p}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {tr.review.practice_suggestions?.length > 0 && (
                    <div className="bg-amber-50 rounded-xl p-4">
                      <h4 className="font-semibold text-amber-900 mb-2">Practice Ideas</h4>
                      <ul className="space-y-1">
                        {tr.review.practice_suggestions.map((s, i) => (
                          <li key={i} className="text-sm text-amber-800">→ {s}</li>
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
            <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
              <div className="p-4 border-b border-slate-100 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">Knowledge Check</h2>
                  <p className="text-sm text-slate-500">{quizQuestions.length} questions • {quizTotalPoints} points</p>
                </div>
                <div className="flex gap-2">
                  {Object.keys(quizResults).length > 0 && !quizArchived && (
                    <button onClick={handleArchiveQuiz} disabled={archivingQuiz}
                            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm hover:bg-emerald-700 disabled:opacity-50">
                      {archivingQuiz ? <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <ArchiveIcon />}
                      Save Results
                    </button>
                  )}
                  {quizArchived && (
                    <span className="flex items-center gap-2 px-4 py-2 bg-emerald-100 text-emerald-700 rounded-lg text-sm">
                      <CheckIcon /> Saved!
                    </span>
                  )}
                  <button onClick={handleRegenerateQuiz} disabled={regeneratingQuiz}
                          className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700 disabled:opacity-50">
                    {regeneratingQuiz ? <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : '🔄'}
                    New Quiz
                  </button>
                </div>
              </div>
              <div className="p-6 space-y-6">
                {quizQuestions.map((q, i) => (
                  <div key={q.id} className={`p-4 rounded-xl border ${
                    quizResults[q.id] ? (quizResults[q.id].correct ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200') : 'bg-slate-50 border-slate-200'
                  }`}>
                    <div className="flex items-start gap-3 mb-3">
                      <span className="w-8 h-8 rounded-full bg-purple-100 text-purple-700 font-bold flex items-center justify-center text-sm">{i + 1}</span>
                      <div>
                        <p className="font-medium text-slate-900">{q.question_text}</p>
                        {q.topic_name && <p className="text-xs text-slate-500 mt-1">{q.topic_name}</p>}
                      </div>
                    </div>
                    {q.options && (
                      <div className="space-y-2 ml-11">
                        {q.options.map((opt, oi) => (
                          <label key={oi} className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer border ${
                            quizAnswers[q.id] === opt ? 'bg-purple-100 border-purple-300' : 'bg-white border-slate-200 hover:bg-slate-50'
                          }`}>
                            <input type="radio" name={q.id} value={opt} checked={quizAnswers[q.id] === opt}
                                   onChange={() => handleAnswerChange(q.id, opt)} disabled={!!quizResults[q.id]} className="w-4 h-4 text-purple-600" />
                            <span className="text-sm">{opt}</span>
                          </label>
                        ))}
                      </div>
                    )}
                    {!quizResults[q.id] && quizAnswers[q.id] && (
                      <div className="ml-11 mt-3">
                        <button onClick={() => handleSubmitAnswer(q.id)} className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700">
                          Check Answer
                        </button>
                      </div>
                    )}
                    {quizResults[q.id] && (
                      <div className={`ml-11 mt-3 p-3 rounded-lg ${quizResults[q.id].correct ? 'bg-emerald-100' : 'bg-red-100'}`}>
                        <div className="flex items-center gap-2 mb-1">
                          {quizResults[q.id].correct ? <CheckIcon /> : <XIcon />}
                          <span className={`font-medium ${quizResults[q.id].correct ? 'text-emerald-700' : 'text-red-700'}`}>
                            {quizResults[q.id].correct ? 'Correct!' : 'Not quite'}
                          </span>
                        </div>
                        <p className={`text-sm ${quizResults[q.id].correct ? 'text-emerald-600' : 'text-red-600'}`}>
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
          <div className="bg-white rounded-2xl border border-slate-200 p-6">
            <h3 className="font-bold text-slate-900 mb-4">📚 Resources</h3>
            <div className="space-y-3">
              {dailyContent?.resources?.slice(0, 6).map((r, i) => (
                r.url ? (
                  <a key={i} href={r.url} target="_blank" rel="noopener noreferrer"
                     className="block p-3 rounded-lg border border-slate-100 hover:border-blue-200 hover:bg-blue-50">
                    <p className="font-medium text-slate-900 text-sm">{r.title}</p>
                    <p className="text-xs text-slate-500 mt-1">{r.type}</p>
                  </a>
                ) : (
                  <div key={i} className="p-3 rounded-lg border border-slate-100">
                    <p className="font-medium text-slate-900 text-sm">{r.title}</p>
                    <p className="text-xs text-slate-500 mt-1">{r.type}</p>
                  </div>
                )
              ))}
            </div>
          </div>

          {userStats && (
            <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl p-6 text-white">
              <h3 className="font-bold mb-4">Your Progress</h3>
              <div className="space-y-3 text-sm">
                <div className="flex justify-between"><span className="text-slate-400">Papers Read</span><span className="font-bold">{userStats.papers_by_status.completed}</span></div>
                <div className="flex justify-between"><span className="text-slate-400">Reading</span><span className="font-bold">{userStats.papers_by_status.reading}</span></div>
                <div className="flex justify-between"><span className="text-slate-400">Topics Reviewed</span><span className="font-bold">{userStats.lifetime.topics_reviewed}</span></div>
                <div className="flex justify-between"><span className="text-slate-400">Quizzes Taken</span><span className="font-bold">{userStats.lifetime.quizzes_taken}</span></div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
