'use client';

import { useState, useEffect } from 'react';

interface ArchivedQuiz {
  id: number;
  topics: string[];
  total_questions: number;
  total_points: number;
  score_earned: number;
  percentage: number;
  duration_seconds?: number;
  taken_at: string;
}

export default function QuizPage() {
  const [quizzes, setQuizzes] = useState<ArchivedQuiz[]>([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({ total: 0, average_score: 0 });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [quizzesRes, statsRes] = await Promise.all([
        fetch('http://localhost:8000/archive/quizzes'),
        fetch('http://localhost:8000/archive/stats'),
      ]);
      const quizzesData = await quizzesRes.json();
      const statsData = await statsRes.json();
      setQuizzes(quizzesData.quizzes || []);
      setStats(statsData.quizzes || { total: 0, average_score: 0 });
    } catch (error) {
      console.error('Failed to fetch:', error);
    } finally {
      setLoading(false);
    }
  };

  const deleteQuiz = async (id: number) => {
    if (!confirm('Delete this quiz from your history?')) return;
    await fetch(`http://localhost:8000/archive/quizzes/${id}`, { method: 'DELETE' });
    fetchData();
  };

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '-';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getScoreColor = (percentage: number) => {
    if (percentage >= 80) return 'text-emerald-600 bg-emerald-100';
    if (percentage >= 60) return 'text-amber-600 bg-amber-100';
    return 'text-red-600 bg-red-100';
  };

  if (loading) {
    return <div className="flex justify-center py-20"><div className="animate-pulse text-slate-500">Loading...</div></div>;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">📝 Quiz History</h1>
          <p className="text-slate-600 mt-1">{stats.total} quizzes • {stats.average_score}% average score</p>
        </div>
        <a href="/" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
          ← Back to Dashboard
        </a>
      </div>

      {/* Stats Cards */}
      {quizzes.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white rounded-xl border border-slate-200 p-4 text-center">
            <div className="text-3xl font-bold text-blue-600">{stats.total}</div>
            <div className="text-sm text-slate-600">Quizzes Taken</div>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-4 text-center">
            <div className="text-3xl font-bold text-emerald-600">{stats.average_score}%</div>
            <div className="text-sm text-slate-600">Average Score</div>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-4 text-center">
            <div className="text-3xl font-bold text-purple-600">
              {quizzes.reduce((sum, q) => sum + q.total_questions, 0)}
            </div>
            <div className="text-sm text-slate-600">Questions Answered</div>
          </div>
        </div>
      )}

      {quizzes.length === 0 ? (
        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
          <h2 className="text-xl font-semibold text-slate-700 mb-2">No Quiz History Yet</h2>
          <p className="text-slate-500">Complete quizzes to track your progress here.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {quizzes.map((quiz) => (
            <div key={quiz.id} className="bg-white rounded-xl border border-slate-200 p-6 hover:shadow-lg transition-all">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`px-3 py-1 text-sm font-bold rounded ${getScoreColor(quiz.percentage)}`}>
                      {quiz.percentage.toFixed(0)}%
                    </span>
                    <span className="text-sm text-slate-500">
                      {quiz.score_earned}/{quiz.total_points} points
                    </span>
                    <span className="text-sm text-slate-500">
                      • {quiz.total_questions} questions
                    </span>
                    {quiz.duration_seconds && (
                      <span className="text-sm text-slate-500">
                        • ⏱️ {formatDuration(quiz.duration_seconds)}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1 mb-2">
                    {quiz.topics?.map((topic, i) => (
                      <span key={i} className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded">
                        {topic}
                      </span>
                    ))}
                  </div>
                  <p className="text-xs text-slate-400">
                    Taken: {new Date(quiz.taken_at).toLocaleString()}
                  </p>
                </div>
                <button onClick={() => deleteQuiz(quiz.id)}
                        className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200">
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
