'use client';

import { useState, useEffect } from 'react';
import {
  getArchivedTopics, updateArchivedTopic, deleteArchivedTopic,
  type ArchivedTopic, type TopicStatus
} from '@/lib/api';

export default function TopicsPage() {
  const [topics, setTopics] = useState<ArchivedTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [editingNotes, setEditingNotes] = useState<number | null>(null);
  const [noteText, setNoteText] = useState('');
  const [statusFilter, setStatusFilter] = useState<TopicStatus | 'all'>('all');

  useEffect(() => {
    fetchTopics();
  }, [statusFilter]);

  const fetchTopics = async () => {
    setLoading(true);
    try {
      const filterStatus = statusFilter === 'all' ? undefined : statusFilter;
      const data = await getArchivedTopics(50, 0, undefined, filterStatus);
      setTopics(data.topics);
    } catch (error) {
      console.error('Failed to fetch topics:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleConfidenceChange = async (topicId: number, level: number) => {
    try {
      await updateArchivedTopic(topicId, { confidence_level: level });
      fetchTopics();
    } catch (error) {
      console.error('Failed to update confidence:', error);
    }
  };

  const handleStatusChange = async (topicId: number, newStatus: TopicStatus) => {
    try {
      await updateArchivedTopic(topicId, { status: newStatus });
      fetchTopics();
    } catch (error) {
      console.error('Failed to update status:', error);
    }
  };

  const handleSaveNotes = async (topicId: number) => {
    try {
      await updateArchivedTopic(topicId, { user_notes: noteText });
      setEditingNotes(null);
      fetchTopics();
    } catch (error) {
      console.error('Failed to save notes:', error);
    }
  };

  const handleDelete = async (topicId: number) => {
    if (!confirm('Remove this topic from your archive?')) return;
    try {
      await deleteArchivedTopic(topicId);
      fetchTopics();
    } catch (error) {
      console.error('Failed to delete topic:', error);
    }
  };

  const StatusBadge = ({ status }: { status: TopicStatus }) => {
    const styles: Record<TopicStatus, string> = {
      active: 'bg-gold/10 text-gold-dark',
      review_later: 'bg-gold/10 text-gold-dark',
      completed: 'bg-moss/10 text-moss',
    };
    const labels: Record<TopicStatus, string> = {
      active: 'Active',
      review_later: 'Review Later',
      completed: 'Completed',
    };
    return (
      <span className={`px-2 py-0.5 text-xs rounded font-medium ${styles[status]}`}>
        {labels[status]}
      </span>
    );
  };

  const ConfidenceLevel = ({ level, topicId }: { level: number; topicId: number }) => {
    const labels = ['Not set', 'Struggling', 'Needs Work', 'Getting There', 'Confident', 'Mastered'];
    const colors = [
      'bg-paper-3 text-ink-2',
      'bg-rust/10 text-rust',
      'bg-gold/10 text-gold-dark',
      'bg-gold/10 text-gold-dark',
      'bg-moss/10 text-moss',
      'bg-gold/10 text-gold-dark',
    ];

    return (
      <div className="flex items-center gap-2">
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              onClick={() => handleConfidenceChange(topicId, n)}
              className={`w-8 h-8 rounded-full text-sm font-medium transition-all ${n <= level
                  ? 'bg-moss text-white'
                  : 'bg-rule text-muted hover:bg-muted'
                }`}
            >
              {n}
            </button>
          ))}
        </div>
        <span className={`px-2 py-1 text-xs rounded ${colors[level] || colors[0]}`}>
          {labels[level] || labels[0]}
        </span>
      </div>
    );
  };

  // Group topics by course
  const topicsByCourse = topics.reduce((acc, topic) => {
    if (!acc[topic.course_name]) {
      acc[topic.course_name] = [];
    }
    acc[topic.course_name].push(topic);
    return acc;
  }, {} as Record<string, ArchivedTopic[]>);

  // Counts for filter tabs
  const allCount = topics.length;
  const activeCount = topics.filter(t => t.status === 'active').length;
  const reviewLaterCount = topics.filter(t => t.status === 'review_later').length;
  const completedCount = topics.filter(t => t.status === 'completed').length;

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="animate-pulse text-muted">Loading topics...</div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-ink">Topic Reviews</h1>
          <p className="text-ink-2 mt-1">
            {topics.length} topics reviewed • {topics.reduce((sum, t) => sum + t.review_count, 0)} total reviews
          </p>
        </div>
        <a href="/" className="px-4 py-2 bg-paper-3 text-ink-2 rounded-lg hover:bg-rule">
          ← Dashboard
        </a>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="bg-paper-2 rounded-xl border border-rule p-4">
          <div className="text-2xl font-bold text-ink">{topics.length}</div>
          <div className="text-sm text-muted">Unique Topics</div>
        </div>
        <div className="bg-paper-2 rounded-xl border border-rule p-4">
          <div className="text-2xl font-bold text-moss">{completedCount}</div>
          <div className="text-sm text-muted">Completed</div>
        </div>
        <div className="bg-paper-2 rounded-xl border border-rule p-4">
          <div className="text-2xl font-bold text-gold-dark">{reviewLaterCount}</div>
          <div className="text-sm text-muted">Review Later</div>
        </div>
        <div className="bg-paper-2 rounded-xl border border-rule p-4">
          <div className="text-2xl font-bold text-gold">{activeCount}</div>
          <div className="text-sm text-muted">Active</div>
        </div>
        <div className="bg-paper-2 rounded-xl border border-rule p-4">
          <div className="text-2xl font-bold text-muted">
            {topics.filter(t => !t.confidence_level).length}
          </div>
          <div className="text-sm text-muted">Not Rated</div>
        </div>
      </div>

      {/* Status Filter Tabs */}
      <div className="flex gap-2">
        {([
          { key: 'all' as const, label: 'All', count: allCount },
          { key: 'active' as const, label: 'Active', count: activeCount },
          { key: 'review_later' as const, label: 'Review Later', count: reviewLaterCount },
          { key: 'completed' as const, label: 'Completed', count: completedCount },
        ]).map(tab => (
          <button
            key={tab.key}
            onClick={() => setStatusFilter(tab.key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              statusFilter === tab.key
                ? 'bg-gold-dark text-white'
                : 'bg-paper-3 text-ink-2 hover:bg-rule'
            }`}
          >
            {tab.label}
            <span className="ml-1.5 opacity-60">({tab.count})</span>
          </button>
        ))}
      </div>

      {/* Topics by Course */}
      {topics.length === 0 ? (
        <div className="bg-paper border border-rule rounded-2xl p-12 text-center">
          <h2 className="text-xl font-semibold text-ink-2 mb-2">No Topics Found</h2>
          <p className="text-muted">
            {statusFilter === 'all'
              ? 'Complete topic reviews from your daily learning to track your progress.'
              : `No topics with status "${statusFilter.replace('_', ' ')}".`}
          </p>
        </div>
      ) : (
        Object.entries(topicsByCourse).map(([courseName, courseTopics]) => (
          <div key={courseName} className="space-y-4">
            <h2 className="text-lg font-bold text-ink flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-moss"></span>
              {courseName}
              <span className="text-sm font-normal text-muted">({courseTopics.length} topics)</span>
            </h2>

            <div className="space-y-3">
              {courseTopics.map((topic) => (
                <div key={topic.id} className={`bg-paper-2 rounded-xl border overflow-hidden ${
                  topic.status === 'completed' ? 'border-moss/25' : 'border-rule'
                }`}>
                  <div className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <h3 className="font-semibold text-ink">{topic.topic_name}</h3>
                          <StatusBadge status={topic.status} />
                          {topic.week_covered && (
                            <span className="px-2 py-0.5 bg-paper-3 text-ink-2 text-xs rounded">
                              Week {topic.week_covered}
                            </span>
                          )}
                          <span className="px-2 py-0.5 bg-gold/10 text-gold-dark text-xs rounded">
                            {topic.review_count}x reviewed
                          </span>
                        </div>

                        <ConfidenceLevel level={topic.confidence_level || 0} topicId={topic.id} />

                        <p className="text-xs text-muted mt-2">
                          Last reviewed: {new Date(topic.last_reviewed_at).toLocaleDateString()}
                          {topic.completed_at && (
                            <span className="ml-2 text-moss">
                              • Completed: {new Date(topic.completed_at).toLocaleDateString()}
                            </span>
                          )}
                        </p>
                      </div>

                      <button
                        onClick={() => setExpandedId(expandedId === topic.id ? null : topic.id)}
                        className="p-2 text-muted hover:text-ink-2"
                      >
                        <svg className={`w-5 h-5 transition-transform ${expandedId === topic.id ? 'rotate-180' : ''}`}
                          fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                    </div>

                    {/* Expanded Content */}
                    {expandedId === topic.id && (
                      <div className="mt-4 pt-4 border-t border-rule space-y-4">
                        {topic.key_points && topic.key_points.length > 0 && (
                          <div className="bg-moss/5 rounded-lg p-4">
                            <h4 className="font-semibold text-moss mb-2">Key Points</h4>
                            <ul className="space-y-1">
                              {topic.key_points.map((point: string, i: number) => (
                                <li key={i} className="text-sm text-moss flex items-start gap-2">
                                  <span className="text-moss">✓</span>
                                  {point}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Status Change Buttons */}
                        <div className="bg-paper rounded-lg p-4">
                          <h4 className="font-semibold text-ink mb-2">Change Status</h4>
                          <div className="flex gap-2">
                            {(['active', 'review_later', 'completed'] as TopicStatus[]).map(s => (
                              <button
                                key={s}
                                onClick={() => handleStatusChange(topic.id, s)}
                                disabled={topic.status === s}
                                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                                  topic.status === s
                                    ? s === 'completed' ? 'bg-moss text-white' :
                                      s === 'review_later' ? 'bg-gold text-white' :
                                      'bg-gold text-white'
                                    : 'bg-paper-2 border border-rule text-ink-2 hover:bg-paper-3'
                                } disabled:cursor-default`}
                              >
                                {s === 'active' ? 'Active' : s === 'review_later' ? 'Review Later' : 'Completed'}
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Notes Section */}
                        <div className="bg-paper rounded-lg p-4">
                          <div className="flex items-center justify-between mb-2">
                            <h4 className="font-semibold text-ink">Your Notes</h4>
                            {editingNotes !== topic.id && (
                              <button
                                onClick={() => {
                                  setEditingNotes(topic.id);
                                  setNoteText(topic.user_notes || '');
                                }}
                                className="text-sm text-gold hover:text-gold-dark"
                              >
                                {topic.user_notes ? 'Edit' : 'Add notes'}
                              </button>
                            )}
                          </div>

                          {editingNotes === topic.id ? (
                            <div className="space-y-2">
                              <textarea
                                value={noteText}
                                onChange={(e) => setNoteText(e.target.value)}
                                placeholder="Add your notes about this topic..."
                                className="bg-paper text-ink w-full px-3 py-2 border border-rule rounded-lg text-sm resize-none h-24 focus:ring-2 focus:ring-gold"
                              />
                              <div className="flex gap-2">
                                <button
                                  onClick={() => handleSaveNotes(topic.id)}
                                  className="px-3 py-1.5 bg-gold-dark text-white text-sm rounded hover:brightness-90"
                                >
                                  Save
                                </button>
                                <button
                                  onClick={() => setEditingNotes(null)}
                                  className="px-3 py-1.5 bg-rule text-ink-2 text-sm rounded hover:bg-muted"
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <p className="text-sm text-ink-2">
                              {topic.user_notes || 'No notes yet.'}
                            </p>
                          )}
                        </div>

                        <div className="flex justify-end">
                          <button
                            onClick={() => handleDelete(topic.id)}
                            className="px-3 py-1.5 text-sm bg-rust/10 text-rust rounded hover:bg-rust/20"
                          >
                            Remove from Archive
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
