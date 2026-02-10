'use client';

import { useState, useEffect } from 'react';
import { getArchivedQuizzes, deleteArchivedQuiz, type ArchivedQuiz } from '@/lib/api';

export default function QuizHistoryPage() {
  const [quizzes, setQuizzes] = useState<ArchivedQuiz[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    fetchQuizzes();
  }, []);

  const fetchQuizzes = async () => {
    setLoading(true);
    try {
      const data = await getArchivedQuizzes(50, 0);
      setQuizzes(data.quizzes);
    } catch (error) {
      console.error('Failed to fetch quizzes:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (quizId: number) => {
    if (!confirm('Delete this quiz from history?')) return;
    try {
      await deleteArchivedQuiz(quizId);
      fetchQuizzes();
    } catch (error) {
      console.error('Failed to delete quiz:', error);
    }
  };

  const getScoreColor = (percentage: number) => {
    if (percentage >= 80) return 'text-emerald-600 bg-emerald-100';
    if (percentage >= 60) return 'text-amber-600 bg-amber-100';
    return 'text-red-600 bg-red-100';
  };

  const getScoreEmoji = (percentage: number) => {
    if (percentage >= 90) return '🌟';
    if (percentage >= 80) return '✨';
    if (percentage >= 70) return '👍';
    if (percentage >= 60) return '📚';
    return '💪';
  };

  // Calculate stats
  const totalQuizzes = quizzes.length;
  const avgScore = quizzes.length > 0 
    ? quizzes.reduce((sum, q) => sum + q.percentage, 0) / quizzes.length 
    : 0;
  const totalQuestions = quizzes.reduce((sum, q) => sum + q.total_questions, 0);
  const perfectScores = quizzes.filter(q => q.percentage === 100).length;

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="animate-pulse text-slate-500">Loading quiz history...</div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">📝 Quiz History</h1>
          <p className="text-slate-600 mt-1">{totalQuizzes} quizzes completed</p>
        </div>
        <a href="/" className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200">
          ← Dashboard
        </a>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="text-2xl font-bold text-slate-900">{totalQuizzes}</div>
          <div className="text-sm text-slate-500">Quizzes Taken</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className={`text-2xl font-bold ${avgScore >= 70 ? 'text-emerald-600' : 'text-amber-600'}`}>
            {avgScore.toFixed(1)}%
          </div>
          <div className="text-sm text-slate-500">Average Score</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="text-2xl font-bold text-blue-600">{totalQuestions}</div>
          <div className="text-sm text-slate-500">Questions Answered</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="text-2xl font-bold text-purple-600">{perfectScores}</div>
          <div className="text-sm text-slate-500">Perfect Scores 🌟</div>
        </div>
      </div>

      {/* Score Distribution Chart */}
      {quizzes.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h2 className="font-bold text-slate-900 mb-4">Score Distribution</h2>
          <div className="flex items-end gap-1 h-32">
            {quizzes.slice(0, 20).reverse().map((quiz, i) => (
              <div
                key={quiz.id}
                className="flex-1 flex flex-col items-center gap-1"
              >
                <div
                  className={`w-full rounded-t ${
                    quiz.percentage >= 80 ? 'bg-emerald-500' :
                    quiz.percentage >= 60 ? 'bg-amber-500' : 'bg-red-400'
                  }`}
                  style={{ height: `${Math.max(quiz.percentage, 10)}%` }}
                  title={`${quiz.percentage.toFixed(0)}%`}
                />
              </div>
            ))}
          </div>
          <div className="flex justify-between text-xs text-slate-400 mt-2">
            <span>Oldest</span>
            <span>Most Recent</span>
          </div>
        </div>
      )}

      {/* Quiz List */}
      {quizzes.length === 0 ? (
        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
          <h2 className="text-xl font-semibold text-slate-700 mb-2">No Quizzes Yet</h2>
          <p className="text-slate-500">Complete quizzes from your daily learning to track your progress.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {quizzes.map((quiz) => (
            <div key={quiz.id} className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-md transition-all">
              <div className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`text-3xl font-bold rounded-xl px-4 py-2 ${getScoreColor(quiz.percentage)}`}>
                      {quiz.percentage.toFixed(0)}%
                      <span className="ml-2">{getScoreEmoji(quiz.percentage)}</span>
                    </div>
                    
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        {quiz.topics.map((topic, i) => (
                          <span key={i} className="px-2 py-1 bg-purple-100 text-purple-700 text-xs rounded">
                            {topic}
                          </span>
                        ))}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-sm text-slate-500">
                        <span>{quiz.total_questions} questions</span>
                        <span>•</span>
                        <span>{quiz.score_earned.toFixed(0)}/{quiz.total_points} points</span>
                        {quiz.duration_seconds && (
                          <>
                            <span>•</span>
                            <span>{Math.round(quiz.duration_seconds / 60)} min</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-slate-400">
                      {new Date(quiz.taken_at).toLocaleDateString()}
                    </span>
                    <button
                      onClick={() => handleDelete(quiz.id)}
                      className="p-2 text-slate-400 hover:text-red-500"
                      title="Delete"
                    >
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tips Based on Performance */}
      {quizzes.length > 5 && avgScore < 70 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6">
          <h3 className="font-bold text-amber-900 mb-2">💡 Study Tips</h3>
          <ul className="space-y-2 text-sm text-amber-800">
            <li>• Review topic summaries before taking quizzes</li>
            <li>• Focus on understanding concepts, not memorizing answers</li>
            <li>• Try explaining topics in your own words</li>
            <li>• Take breaks between study sessions for better retention</li>
          </ul>
        </div>
      )}

      {quizzes.length > 5 && avgScore >= 85 && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-6">
          <h3 className="font-bold text-emerald-900 mb-2">🎉 Great Job!</h3>
          <p className="text-sm text-emerald-800">
            You're averaging {avgScore.toFixed(0)}% across {totalQuizzes} quizzes. 
            Consider challenging yourself with harder questions or exploring new topics!
          </p>
        </div>
      )}
    </div>
  );
}
