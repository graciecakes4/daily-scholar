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
      unread: 'bg-slate-100 text-slate-700',
      reading: 'bg-amber-100 text-amber-700',
      completed: 'bg-emerald-100 text-emerald-700',
    };
    
    return (
      <select
        value={status}
        onChange={(e) => handleStatusChange(paperId, e.target.value)}
        className={`px-2 py-1 text-xs font-medium rounded cursor-pointer ${colors[status] || colors.unread}`}
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
          className={`text-lg ${star <= rating ? 'text-yellow-400' : 'text-slate-300'} hover:text-yellow-400`}
        >
          ★
        </button>
      ))}
    </div>
  );

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="animate-pulse text-slate-500">Loading papers...</div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">📚 Paper Archive</h1>
          <p className="text-slate-600 mt-1">{papers.length} papers saved</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowUploadModal(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            Upload PDF
          </button>
          <a href="/" className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200">
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
              filter === status ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {status.charAt(0).toUpperCase() + status.slice(1)}
          </button>
        ))}
      </div>

      {/* Papers List */}
      {papers.length === 0 ? (
        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
          <h2 className="text-xl font-semibold text-slate-700 mb-2">No Papers Yet</h2>
          <p className="text-slate-500">Archive papers from your daily learning or upload PDFs directly.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {papers.map((paper) => (
            <div key={paper.id} className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-lg transition-all">
              <div className="p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <StatusBadge status={paper.read_status} paperId={paper.id} />
                      <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded">{paper.source}</span>
                      {paper.has_local_pdf && (
                        <span className="px-2 py-1 bg-green-100 text-green-700 text-xs rounded flex items-center gap-1">
                          📄 PDF Saved
                        </span>
                      )}
                    </div>
                    <h3 className="text-lg font-semibold text-slate-900 mb-1">{paper.title}</h3>
                    <p className="text-sm text-slate-600 mb-2">
                      {paper.authors?.slice(0, 3).join(', ')}{paper.authors?.length > 3 && '...'}
                    </p>
                    <div className="flex items-center gap-4">
                      <StarRating rating={paper.user_rating || 0} paperId={paper.id} />
                      <span className="text-xs text-slate-400">
                        Archived {new Date(paper.archived_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => setExpandedId(expandedId === paper.id ? null : paper.id)}
                    className="p-2 text-slate-400 hover:text-slate-600"
                  >
                    <svg className={`w-5 h-5 transition-transform ${expandedId === paper.id ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                </div>

                {/* Expanded Content */}
                {expandedId === paper.id && (
                  <div className="mt-4 pt-4 border-t border-slate-100 space-y-4">
                    {paper.summary && (
                      <div className="bg-blue-50 rounded-lg p-4">
                        <h4 className="font-semibold text-blue-900 mb-2">Summary</h4>
                        <p className="text-sm text-blue-800">{paper.summary}</p>
                      </div>
                    )}
                    
                    {paper.abstract && (
                      <div>
                        <h4 className="font-semibold text-slate-900 mb-2">Abstract</h4>
                        <p className="text-sm text-slate-700">{paper.abstract}</p>
                      </div>
                    )}

                    {/* PDF Actions */}
                    <div className="flex items-center gap-2 flex-wrap">
                      {paper.url && (
                        <a href={paper.url} target="_blank" rel="noopener noreferrer"
                           className="px-3 py-1.5 text-sm bg-slate-100 text-slate-700 rounded hover:bg-slate-200">
                          Open Source →
                        </a>
                      )}
                      
                      {paper.has_local_pdf ? (
                        <a href={getPaperPdfUrl(paper.id)} target="_blank" rel="noopener noreferrer"
                           className="px-3 py-1.5 text-sm bg-green-100 text-green-700 rounded hover:bg-green-200">
                          📄 View Local PDF
                        </a>
                      ) : (
                        <>
                          {paper.pdf_url && (
                            <button
                              onClick={() => handlePdfDownload(paper.id)}
                              disabled={downloadingPdf === paper.id}
                              className="px-3 py-1.5 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200 disabled:opacity-50"
                            >
                              {downloadingPdf === paper.id ? 'Downloading...' : '⬇️ Download PDF'}
                            </button>
                          )}
                          <label className="px-3 py-1.5 text-sm bg-purple-100 text-purple-700 rounded hover:bg-purple-200 cursor-pointer">
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
                        className="px-3 py-1.5 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200 ml-auto"
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
          <div className="bg-white rounded-2xl p-6 max-w-md w-full mx-4">
            <h2 className="text-xl font-bold text-slate-900 mb-4">Upload a Paper</h2>
            <p className="text-slate-600 text-sm mb-4">
              Upload a PDF to add it to your reading archive.
            </p>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Paper Title (optional)
                </label>
                <input
                  type="text"
                  value={standaloneTitle}
                  onChange={(e) => setStandaloneTitle(e.target.value)}
                  placeholder="Will use filename if empty"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  PDF File
                </label>
                <input
                  ref={standaloneFileRef}
                  type="file"
                  accept=".pdf"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowUploadModal(false)}
                className="flex-1 px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200"
              >
                Cancel
              </button>
              <button
                onClick={handleStandaloneUpload}
                disabled={uploadingStandalone}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
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
