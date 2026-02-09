'use client';

import { useState, useEffect } from 'react';
import { getDailyContent, checkHealth, regenerateQuiz, type DailyContent, type QuizQuestion } from '@/lib/api';

// Simple SVG icons
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

const ClockIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const ExternalLinkIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
  </svg>
);

const CheckIcon = () => (
  <svg className="w-5 h-5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const XIcon = () => (
  <svg className="w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const InfoIcon = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

export default function DashboardPage() {
  const [dailyContent, setDailyContent] = useState<DailyContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<'paper' | 'review' | 'quiz'>('review'); // Default to review since papers may not be available
  const [quizAnswers, setQuizAnswers] = useState<Record<string, string>>({});
  const [quizResults, setQuizResults] = useState<Record<string, { correct: boolean; feedback: string }>>({});
  const [apiStatus, setApiStatus] = useState<'checking' | 'connected' | 'error'>('checking');
  const [regeneratingQuiz, setRegeneratingQuiz] = useState(false);
  const [quizQuestions, setQuizQuestions] = useState<QuizQuestion[]>([]);
  const [quizTotalPoints, setQuizTotalPoints] = useState(0);

  useEffect(() => {
    async function loadContent() {
      try {
        await checkHealth();
        setApiStatus('connected');
        const content = await getDailyContent();
        setDailyContent(content);
        
        // Set quiz state
        setQuizQuestions(content.quiz.questions);
        setQuizTotalPoints(content.quiz.total_points);
        
        // Auto-select the best available tab
        if (content.paper) {
          setActiveSection('paper');
        } else if (content.topic_reviews.length > 0) {
          setActiveSection('review');
        } else if (content.quiz.questions.length > 0) {
          setActiveSection('quiz');
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
    try {
      const newQuiz = await regenerateQuiz(5, 'medium');
      setQuizQuestions(newQuiz.questions);
      setQuizTotalPoints(newQuiz.total_points);
      // Clear previous answers and results
      setQuizAnswers({});
      setQuizResults({});
    } catch (err) {
      console.error('Failed to regenerate quiz:', err);
    } finally {
      setRegeneratingQuiz(false);
    }
  };

  // Loading state
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

  // API error state
  if (apiStatus === 'error') {
    return (
      <div className="max-w-2xl mx-auto mt-12">
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-8 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-amber-100 flex items-center justify-center">
            <svg className="w-8 h-8 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-amber-900 mb-2">Backend Not Connected</h2>
          <p className="text-amber-700 mb-6">Make sure the backend server is running:</p>
          <div className="bg-amber-100/50 rounded-lg p-4 text-left font-mono text-sm text-amber-800">
            <p>cd ~/daily-scholar</p>
            <p>source venv/bin/activate</p>
            <p>uvicorn backend.main:app --reload</p>
          </div>
          <button 
            onClick={() => window.location.reload()}
            className="mt-6 px-6 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors"
          >
            Retry Connection
          </button>
        </div>
      </div>
    );
  }

  if (error || !dailyContent) {
    return (
      <div className="max-w-2xl mx-auto mt-12">
        <div className="bg-red-50 border border-red-200 rounded-2xl p-8 text-center">
          <h2 className="text-xl font-semibold text-red-900 mb-2">Error Loading Content</h2>
          <p className="text-red-700">{error || 'Unknown error occurred'}</p>
        </div>
      </div>
    );
  }

  // Check what content is available
  const hasPaper = dailyContent.paper !== null;
  const hasReviews = dailyContent.topic_reviews.length > 0;
  const hasQuiz = quizQuestions.length > 0;

  return (
    <div className="space-y-8 animate-in">
      {/* Header */}
      <header className="text-center py-8">
        <p className="text-sm font-medium text-blue-600 mb-2">
          {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
        </p>
        <h1 className="text-4xl font-bold bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 bg-clip-text text-transparent mb-4">
          Your Daily Learning
        </h1>
        <div className="flex items-center justify-center gap-2 text-slate-500">
          <ClockIcon />
          <span>Estimated time: {dailyContent.estimated_time_minutes} minutes</span>
        </div>
      </header>

      {/* Navigation Tabs */}
      <div className="flex justify-center">
        <div className="inline-flex bg-white rounded-xl p-1.5 shadow-lg shadow-slate-200/50 border border-slate-200/50">
          {[
            { id: 'paper', label: "Today's Paper", icon: <BookIcon />, available: hasPaper },
            { id: 'review', label: 'Topic Review', icon: <BrainIcon />, available: hasReviews },
            { id: 'quiz', label: 'Quiz', icon: <QuizIcon />, available: hasQuiz },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveSection(tab.id as any)}
              className={`flex items-center gap-2 px-6 py-3 rounded-lg text-sm font-medium transition-all ${
                activeSection === tab.id
                  ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/25'
                  : tab.available
                    ? 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                    : 'text-slate-400 cursor-not-allowed'
              }`}
              disabled={!tab.available}
            >
              {tab.icon}
              {tab.label}
              {!tab.available && <span className="text-xs opacity-60">(N/A)</span>}
            </button>
          ))}
        </div>
      </div>

      {/* Paper Section */}
      {activeSection === 'paper' && (
        <div className="max-w-4xl mx-auto space-y-6">
          {hasPaper && dailyContent.paper ? (
            <div className="bg-white rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-200/50 overflow-hidden">
              <div className="p-8">
                <div className="flex items-start justify-between gap-4 mb-6">
                  <div>
                    <span className="inline-block px-3 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded-full mb-3">
                      {dailyContent.paper.primary_category || dailyContent.paper.source}
                    </span>
                    <h2 className="text-2xl font-bold text-slate-900 leading-tight">
                      {dailyContent.paper.title}
                    </h2>
                  </div>
                  <a
                    href={dailyContent.paper.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition-colors shrink-0"
                  >
                    <span className="text-sm font-medium">Open Paper</span>
                    <ExternalLinkIcon />
                  </a>
                </div>
                
                <p className="text-slate-600 mb-4">
                  <span className="font-medium">Authors:</span> {dailyContent.paper.authors.slice(0, 5).join(', ')}
                  {dailyContent.paper.authors.length > 5 && '...'}
                </p>
                
                <div className="flex items-center gap-4 text-sm text-slate-500">
                  <span>Relevance: {Math.round(dailyContent.paper.relevance_score * 100)}%</span>
                  {dailyContent.paper.published_date && (
                    <span>Published: {dailyContent.paper.published_date}</span>
                  )}
                </div>
              </div>
              
              {dailyContent.paper_summary && (
                <div className="border-t border-slate-100 bg-slate-50/50 p-8">
                  <h3 className="text-lg font-semibold text-slate-900 mb-4">AI-Generated Summary</h3>
                  <div className="prose-scholar">
                    <p className="whitespace-pre-wrap">{dailyContent.paper_summary.summary}</p>
                  </div>
                  
                  {dailyContent.paper_summary.key_findings.length > 0 && (
                    <div className="mt-6">
                      <h4 className="font-semibold text-slate-800 mb-3">Key Findings</h4>
                      <ul className="space-y-2">
                        {dailyContent.paper_summary.key_findings.map((finding, i) => (
                          <li key={i} className="flex items-start gap-2 text-slate-700">
                            <span className="w-5 h-5 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-medium shrink-0 mt-0.5">
                              {i + 1}
                            </span>
                            {finding}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {dailyContent.paper_summary.relevance_explanation && (
                    <div className="mt-6 p-4 bg-blue-50 rounded-xl">
                      <h4 className="font-semibold text-blue-900 mb-2">Why This Matters for You</h4>
                      <p className="text-blue-800">{dailyContent.paper_summary.relevance_explanation}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="bg-slate-50 border border-slate-200 rounded-2xl p-8 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
                <InfoIcon />
              </div>
              <h2 className="text-xl font-semibold text-slate-700 mb-2">No Paper Available Today</h2>
              <p className="text-slate-500 max-w-md mx-auto">
                Paper discovery is temporarily unavailable due to API rate limits. 
                Check back later or explore the Topic Reviews and Quiz sections!
              </p>
            </div>
          )}
        </div>
      )}

      {/* Review Section */}
      {activeSection === 'review' && (
        <div className="max-w-4xl mx-auto space-y-6">
          {hasReviews ? (
            dailyContent.topic_reviews.map((tr, index) => (
              <div key={index} className="bg-white rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-200/50 overflow-hidden">
                <div className="p-8">
                  <div className="flex items-center gap-3 mb-6">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center text-white">
                      <BrainIcon />
                    </div>
                    <div>
                      <p className="text-sm text-slate-500">{tr.topic.course_name}</p>
                      <h3 className="text-xl font-bold text-slate-900">{tr.topic.name}</h3>
                    </div>
                  </div>
                  
                  <div className="prose-scholar">
                    <p className="whitespace-pre-wrap">{tr.review.review_content}</p>
                  </div>
                  
                  {tr.review.key_points.length > 0 && (
                    <div className="mt-6 p-4 bg-emerald-50 rounded-xl">
                      <h4 className="font-semibold text-emerald-900 mb-3">Key Points</h4>
                      <ul className="space-y-2">
                        {tr.review.key_points.map((point, i) => (
                          <li key={i} className="flex items-start gap-2 text-emerald-800">
                            <CheckIcon />
                            {point}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {tr.review.connections.length > 0 && (
                    <div className="mt-6">
                      <h4 className="font-semibold text-slate-800 mb-3">Connections to Other Topics</h4>
                      <ul className="space-y-2">
                        {tr.review.connections.map((connection, i) => (
                          <li key={i} className="flex items-start gap-2 text-slate-700">
                            <span className="text-blue-500">→</span>
                            {connection}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {tr.review.practice_suggestions.length > 0 && (
                    <div className="mt-6">
                      <h4 className="font-semibold text-slate-800 mb-3">Practice Suggestions</h4>
                      <div className="grid gap-3">
                        {tr.review.practice_suggestions.map((suggestion, i) => (
                          <div key={i} className="flex items-start gap-3 p-3 bg-slate-50 rounded-lg">
                            <span className="w-6 h-6 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center text-xs font-medium shrink-0">
                              {i + 1}
                            </span>
                            <p className="text-slate-700">{suggestion}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="bg-slate-50 border border-slate-200 rounded-2xl p-8 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
                <InfoIcon />
              </div>
              <h2 className="text-xl font-semibold text-slate-700 mb-2">No Reviews Available</h2>
              <p className="text-slate-500">Check your courses.yaml configuration to add topics for review.</p>
            </div>
          )}
        </div>
      )}

      {/* Quiz Section */}
      {activeSection === 'quiz' && (
        <div className="max-w-3xl mx-auto space-y-6">
          {hasQuiz ? (
            <>
              <div className="text-center mb-8">
                <h2 className="text-2xl font-bold text-slate-900 mb-2">Knowledge Check</h2>
                <p className="text-slate-600 mb-4">
                  {quizQuestions.length} questions • {quizTotalPoints} points possible
                </p>
                <button
                  onClick={handleRegenerateQuiz}
                  disabled={regeneratingQuiz}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition-colors disabled:opacity-50"
                >
                  {regeneratingQuiz ? (
                    <>
                      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Generating...
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      Generate New Quiz
                    </>
                  )}
                </button>
              </div>
              
              {quizQuestions.map((question, index) => {
                const result = quizResults[question.id];
                const answered = !!result;
                
                return (
                  <div 
                    key={question.id} 
                    className={`bg-white rounded-2xl shadow-xl shadow-slate-200/50 border overflow-hidden transition-all ${
                      answered 
                        ? result.correct ? 'border-emerald-200' : 'border-amber-200'
                        : 'border-slate-200/50'
                    }`}
                  >
                    <div className="p-6">
                      <div className="flex items-start justify-between gap-4 mb-4">
                        <div className="flex items-center gap-3">
                          <span className="w-8 h-8 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center text-sm font-medium">
                            {index + 1}
                          </span>
                          <span className="text-xs text-slate-500 capitalize">{question.difficulty}</span>
                        </div>
                        <span className="text-sm text-slate-500">{question.points} pt{question.points > 1 ? 's' : ''}</span>
                      </div>
                      
                      <p className="text-lg text-slate-900 mb-4">{question.question_text}</p>
                      
                      {question.question_type === 'multiple_choice' && question.options && (
                        <div className="space-y-2 mb-4">
                          {question.options.map((option, i) => (
                            <label 
                              key={i}
                              className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-all ${
                                quizAnswers[question.id] === option
                                  ? 'border-blue-500 bg-blue-50'
                                  : 'border-slate-200 hover:border-slate-300'
                              } ${answered ? 'pointer-events-none opacity-75' : ''}`}
                            >
                              <input
                                type="radio"
                                name={question.id}
                                value={option}
                                checked={quizAnswers[question.id] === option}
                                onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                                className="w-4 h-4 text-blue-600"
                                disabled={answered}
                              />
                              <span className="text-slate-700">{option}</span>
                            </label>
                          ))}
                        </div>
                      )}
                      
                      {(question.question_type === 'short_answer' || question.question_type === 'explain_concept') && (
                        <textarea
                          value={quizAnswers[question.id] || ''}
                          onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                          placeholder="Type your answer here..."
                          className="w-full p-4 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                          rows={3}
                          disabled={answered}
                        />
                      )}
                      
                      {question.question_type === 'true_false' && (
                        <div className="flex gap-4 mb-4">
                          {['True', 'False'].map((option) => (
                            <button
                              key={option}
                              onClick={() => handleAnswerChange(question.id, option)}
                              className={`flex-1 py-3 px-6 rounded-lg border font-medium transition-all ${
                                quizAnswers[question.id] === option
                                  ? 'border-blue-500 bg-blue-50 text-blue-700'
                                  : 'border-slate-200 hover:border-slate-300 text-slate-700'
                              } ${answered ? 'pointer-events-none opacity-75' : ''}`}
                              disabled={answered}
                            >
                              {option}
                            </button>
                          ))}
                        </div>
                      )}
                      
                      {!answered && quizAnswers[question.id] && (
                        <button
                          onClick={() => handleSubmitAnswer(question.id)}
                          className="mt-4 px-6 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-lg font-medium hover:shadow-lg transition-all"
                        >
                          Submit Answer
                        </button>
                      )}
                      
                      {answered && (
                        <div className={`mt-4 p-4 rounded-lg ${result.correct ? 'bg-emerald-100' : 'bg-amber-100'}`}>
                          <div className="flex items-center gap-2 mb-2">
                            {result.correct ? <CheckIcon /> : <XIcon />}
                            <span className={`font-semibold ${result.correct ? 'text-emerald-800' : 'text-amber-800'}`}>
                              {result.correct ? 'Correct!' : 'Not quite'}
                            </span>
                          </div>
                          <p className={result.correct ? 'text-emerald-700' : 'text-amber-700'}>
                            {result.feedback}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </>
          ) : (
            <div className="bg-slate-50 border border-slate-200 rounded-2xl p-8 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
                <InfoIcon />
              </div>
              <h2 className="text-xl font-semibold text-slate-700 mb-2">No Quiz Available</h2>
              <p className="text-slate-500">Quiz generation encountered an error. Try refreshing the page.</p>
            </div>
          )}
        </div>
      )}

      {/* Resources Section */}
      {dailyContent.resources.length > 0 && (
        <div className="max-w-4xl mx-auto mt-12">
          <h2 className="text-xl font-bold text-slate-900 mb-4">Supplementary Resources</h2>
          <div className="grid md:grid-cols-2 gap-4">
            {dailyContent.resources.map((resource, i) => {
              // Determine the URL to use
              const resourceUrl = resource.url || 
                (resource.search_term ? `https://www.google.com/search?q=${encodeURIComponent(resource.search_term)}` : null);
              
              const ResourceWrapper = resourceUrl ? 'a' : 'div';
              const wrapperProps = resourceUrl ? {
                href: resourceUrl,
                target: "_blank",
                rel: "noopener noreferrer"
              } : {};
              
              return (
                <ResourceWrapper
                  key={i}
                  {...wrapperProps}
                  className={`bg-white rounded-xl p-4 border border-slate-200/50 transition-all group ${
                    resourceUrl ? 'hover:shadow-lg hover:border-blue-200 cursor-pointer' : ''
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="flex flex-col gap-1">
                      <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs font-medium rounded capitalize group-hover:bg-blue-100 group-hover:text-blue-700 transition-colors w-fit">
                        {resource.type}
                      </span>
                      {resource.source && (
                        <span className="px-2 py-0.5 bg-slate-50 text-slate-400 text-xs rounded w-fit">
                          {resource.source}
                        </span>
                      )}
                    </div>
                    <div className="flex-1">
                      <h3 className="font-medium text-slate-900 mb-1 group-hover:text-blue-700 transition-colors flex items-center gap-2">
                        {resource.title}
                        {resourceUrl && (
                          <svg className="w-3 h-3 text-slate-400 group-hover:text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                          </svg>
                        )}
                      </h3>
                      <p className="text-sm text-slate-600">{resource.description}</p>
                      {resource.pdf_url && (
                        <a 
                          href={resource.pdf_url} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 mt-2 text-xs text-blue-600 hover:text-blue-800"
                        >
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                          PDF Available
                        </a>
                      )}
                    </div>
                  </div>
                </ResourceWrapper>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
