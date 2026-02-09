import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Daily Scholar',
  description: 'Your personalized daily learning companion for research and study',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50">
        <div className="min-h-screen">
          {/* Navigation */}
          <nav className="sticky top-0 z-50 backdrop-blur-xl bg-white/70 border-b border-slate-200/50">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex items-center justify-between h-16">
                <a href="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                    <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                    </svg>
                  </div>
                  <span className="text-xl font-semibold bg-gradient-to-r from-slate-900 to-slate-700 bg-clip-text text-transparent">
                    Daily Scholar
                  </span>
                </a>
                
                <div className="flex items-center gap-2">
                  <a href="/papers" className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-all">
                    Papers
                  </a>
                  <a href="/topics" className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-all">
                    Topics
                  </a>
                  <a href="/quiz" className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-all">
                    Quizzes
                  </a>
                  <a 
                    href="http://localhost:8000/docs" 
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 transition-all"
                  >
                    API
                  </a>
                </div>
              </div>
            </div>
          </nav>

          {/* Main Content */}
          <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {children}
          </main>

          {/* Footer */}
          <footer className="border-t border-slate-200/50 mt-auto">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
              <div className="flex items-center justify-between">
                <p className="text-sm text-slate-500">
                  Daily Scholar — Your personalized learning companion
                </p>
                <div className="flex items-center gap-4 text-sm text-slate-400">
                  <a href="http://localhost:8000/docs" target="_blank" rel="noopener noreferrer" className="hover:text-slate-600 transition-colors">
                    Swagger UI
                  </a>
                  <span>•</span>
                  <a href="http://localhost:8000/redoc" target="_blank" rel="noopener noreferrer" className="hover:text-slate-600 transition-colors">
                    ReDoc
                  </a>
                </div>
              </div>
            </div>
          </footer>
        </div>
      </body>
    </html>
  )
}
