'use client';

import { useState, useEffect, useRef } from 'react';
import { 
  getArchivedPapers, updateArchivedPaper, deleteArchivedPaper,
  uploadPdfToPaper, downloadPdfFromUrl, uploadStandalonePdf, getPaperPdfUrl,
  type ArchivedPaper 
} from '@/lib/api';

export default function PapersPage() {
  const [papers, setPapers] = useState<ArchivedPaper[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [uploadingPdf, setUploadingPdf] = useState<number | null>(null);
  const [downloadingPdf, setDownloadingPdf] = useState<number | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadingStandalone, setUploadingStandalone] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const standaloneFileRef = useRef<HTMLInputElement>(null);
  const [standaloneTitle, setStandaloneTitle] = useState('');

  useEffect(() => {
    fetchPapers();
  }, [filter]);

  const fetchPapers = async () => {
    setLoading(true);
    try {
      const status = filter !== 'all' ? filter : undefined;
      const data = await getArchivedPapers(50, 0, status);
      setPapers(data.papers);
    } catch (error) {
      console.error('Failed to fetch papers:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleStatusChange = async (paperId: number, newStatus: string) => {
    try {
      await updateArchivedPaper(paperId, { read_status: newStatus });
      fetchPapers();
    } catch (error) {
      console.error('Failed to update status:', error);
    }
  };

  const handleRatingChange = async (paperId: number, rating: number) => {
    try {
      await updateArchivedPaper(paperId, { user_rating: rating });
      fetchPapers();
    } catch (error) {
      console.error('Failed to update rating:', error);
    }
  };

  const handleDelete = async (paperId: number) => {
    if (!confirm('Delete this paper from your archive?')) return;
    try {
      await deleteArchivedPaper(paperId);
      fetchPapers();
    } catch (error) {
      console.error('Failed to delete paper:', error);
    }
  };

  const handlePdfUpload = async (paperId: number, file: File) => {
    setUploadingPdf(paperId);
    try {
      await uploadPdfToPaper(paperId, file);
      fetchPapers();
    } catch (error) {
      console.error('Failed to upload PDF:', error);
      alert('Failed to upload PDF');
    } finally {
      setUploadingPdf(null);
    }
  };

  const handlePdfDownload = async (paperId: number) => {
    setDownloadingPdf(paperId);
    try {
      await downloadPdfFromUrl(paperId);
      fetchPapers();
    } catch (error) {
      console.error('Failed to download PDF:', error);
      alert('Failed to download PDF from source');
    } finally {
      setDownloadingPdf(null);
    }
  };

  const handleStandaloneUpload = async () => {
    const file = standaloneFileRef.current?.files?.[0];
    if (!file) return;
    
    setUploadingStandalone(true);
    try {
      await uploadStandalonePdf(file, standaloneTitle || undefined);
      setShowUploadModal(false);
      setStandaloneTitle('');
      fetchPapers();
    } catch (error) {
      console.error('Failed to upload PDF:', error);
      alert('Failed to upload PDF');
    } finally {
      setUploadingStandalone(false);
    }
  };

  const StatusBadge = ({ status, paperId }: { status: string; paperId: number }) => {
    const colors: Record<string, string> = {
      unread: 'bg-paper-3 text-ink-2',
      reading: 'bg-gold/10 text-gold-dark',
      completed: 'bg-moss/10 text-moss',
    };
    
    return (
      <select
        value={status}
        onChange={(e) => handleStatusChange(paperId, e.target.value)}
        className={`bg-paper text-ink px-2 py-1 text-xs font-medium rounded cursor-pointer ${colors[status] || colors.unread}`}
      >
        <option value="unread">Unread</option>
        <option value="reading">Reading</option>
        <option value="completed">Completed</option>
      </select>
    );
  };

  const StarRating = ({ rating, paperId }: { rating: number; paperId: number }) => (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          onClick={() => handleRatingChange(paperId, star)}
          className={`text-lg ${star <= rating ? 'text-gold' : 'text-muted'} hover:text-gold`}
        >
          ★
        </button>
      ))}
    </div>
  );

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="animate-pulse text-muted">Loading papers...</div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-serif text-3xl font-bold text-ink">📚 Paper Archive</h1>
          <p className="text-ink-2 mt-1">{papers.length} papers saved</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowUploadModal(true)}
            className="px-4 py-2 bg-gold-dark text-white rounded-lg hover:brightness-90 flex items-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            Upload PDF
          </button>
          <a href="/" className="px-4 py-2 bg-paper-3 text-ink-2 rounded-lg hover:bg-rule">
            ← Dashboard
          </a>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        {['all', 'unread', 'reading', 'completed'].map((status) => (
          <button
            key={status}
            onClick={() => setFilter(status)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              filter === status ? 'bg-gold-dark text-white' : 'bg-paper-3 text-ink-2 hover:bg-rule'
            }`}
          >
            {status.charAt(0).toUpperCase() + status.slice(1)}
          </button>
        ))}
      </div>

      {/* Papers List */}
      {papers.length === 0 ? (
        <div className="bg-paper border border-rule rounded-2xl p-12 text-center">
          <h2 className="text-xl font-semibold text-ink-2 mb-2">No Papers Yet</h2>
          <p className="text-muted">Archive papers from your daily learning or upload PDFs directly.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {papers.map((paper) => (
            <div key={paper.id} className="bg-paper-2 rounded-xl border border-rule overflow-hidden hover:shadow-lg transition-all">
              <div className="p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <StatusBadge status={paper.read_status} paperId={paper.id} />
                      <span className="px-2 py-1 bg-paper-3 text-ink-2 text-xs rounded">{paper.source}</span>
                      {paper.has_local_pdf && (
                        <span className="px-2 py-1 bg-moss/10 text-moss text-xs rounded flex items-center gap-1">
                          📄 PDF Saved
                        </span>
                      )}
                    </div>
                    <h3 className="text-lg font-semibold text-ink mb-1">{paper.title}</h3>
                    <p className="text-sm text-ink-2 mb-2">
                      {paper.authors?.slice(0, 3).join(', ')}{paper.authors?.length > 3 && '...'}
                    </p>
                    <div className="flex items-center gap-4">
                      <StarRating rating={paper.user_rating || 0} paperId={paper.id} />
                      <span className="text-xs text-muted">
                        Archived {new Date(paper.archived_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => setExpandedId(expandedId === paper.id ? null : paper.id)}
                    className="p-2 text-muted hover:text-ink-2"
                  >
                    <svg className={`w-5 h-5 transition-transform ${expandedId === paper.id ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                </div>

                {/* Expanded Content */}
                {expandedId === paper.id && (
                  <div className="mt-4 pt-4 border-t border-rule space-y-4">
                    {paper.summary && (
                      <div className="bg-gold/5 rounded-lg p-4">
                        <h4 className="font-semibold text-gold-dark mb-2">Summary</h4>
                        <p className="text-sm text-gold-dark">{paper.summary}</p>
                      </div>
                    )}
                    
                    {paper.abstract && (
                      <div>
                        <h4 className="font-semibold text-ink mb-2">Abstract</h4>
                        <p className="text-sm text-ink-2">{paper.abstract}</p>
                      </div>
                    )}

                    {/* PDF Actions */}
                    <div className="flex items-center gap-2 flex-wrap">
                      {paper.url && (
                        <a href={paper.url} target="_blank" rel="noopener noreferrer"
                           className="px-3 py-1.5 text-sm bg-paper-3 text-ink-2 rounded hover:bg-rule">
                          Open Source →
                        </a>
                      )}
                      
                      {paper.has_local_pdf ? (
                        <a href={getPaperPdfUrl(paper.id)} target="_blank" rel="noopener noreferrer"
                           className="px-3 py-1.5 text-sm bg-moss/10 text-moss rounded hover:bg-moss/20">
                          📄 View Local PDF
                        </a>
                      ) : (
                        <>
                          {paper.pdf_url && (
                            <button
                              onClick={() => handlePdfDownload(paper.id)}
                              disabled={downloadingPdf === paper.id}
                              className="px-3 py-1.5 text-sm bg-gold/10 text-gold-dark rounded hover:bg-gold/20 disabled:opacity-50"
                            >
                              {downloadingPdf === paper.id ? 'Downloading...' : '⬇️ Download PDF'}
                            </button>
                          )}
                          <label className="px-3 py-1.5 text-sm bg-gold/10 text-gold-dark rounded hover:bg-gold/20 cursor-pointer">
                            📤 Upload PDF
                            <input
                              type="file"
                              accept=".pdf"
                              className="hidden"
                              onChange={(e) => {
                                const file = e.target.files?.[0];
                                if (file) handlePdfUpload(paper.id, file);
                              }}
                            />
                          </label>
                        </>
                      )}
                      
                      <button
                        onClick={() => handleDelete(paper.id)}
                        className="px-3 py-1.5 text-sm bg-rust/10 text-rust rounded hover:bg-rust/20 ml-auto"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-paper-2 rounded-2xl p-6 max-w-md w-full mx-4">
            <h2 className="font-serif text-xl font-bold text-ink mb-4">Upload a Paper</h2>
            <p className="text-ink-2 text-sm mb-4">
              Upload a PDF to add it to your reading archive.
            </p>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink-2 mb-1">
                  Paper Title (optional)
                </label>
                <input
                  type="text"
                  value={standaloneTitle}
                  onChange={(e) => setStandaloneTitle(e.target.value)}
                  placeholder="Will use filename if empty"
                  className="bg-paper text-ink w-full px-3 py-2 border border-rule rounded-lg focus:ring-2 focus:ring-gold focus:border-gold/40"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-ink-2 mb-1">
                  PDF File
                </label>
                <input
                  ref={standaloneFileRef}
                  type="file"
                  accept=".pdf"
                  className="w-full px-3 py-2 border border-rule rounded-lg"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowUploadModal(false)}
                className="flex-1 px-4 py-2 bg-paper-3 text-ink-2 rounded-lg hover:bg-rule"
              >
                Cancel
              </button>
              <button
                onClick={handleStandaloneUpload}
                disabled={uploadingStandalone}
                className="flex-1 px-4 py-2 bg-gold-dark text-white rounded-lg hover:brightness-90 disabled:opacity-50"
              >
                {uploadingStandalone ? 'Uploading...' : 'Upload'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
