import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Link from "next/link";
import InstallPrompt from "@/components/InstallPrompt";
import AuthBoundary from "@/components/AuthBoundary";
import DashboardTour from "@/components/DashboardTour";
import MobileTabBar from "@/components/MobileTabBar";
import OnboardingGuard from "@/components/OnboardingGuard";
import ScopePickerGuard from "@/components/ScopePickerGuard";
import ScopeTour from "@/components/ScopeTour";
import TopicsTour from "@/components/TopicsTour";
import UserMenu from "@/components/UserMenu";
import { API_BASE } from "@/lib/api";

const inter = Inter({ subsets: ["latin"] });

// PWA-aware metadata. The viewport export drives the <meta name="theme-color">
// so the browser chrome (iOS Safari status bar, Android task switcher card)
// matches the app's deep-slate background.
export const metadata: Metadata = {
  title: "Daily Scholar",
  description: "Your personalized daily learning companion",
  applicationName: "Daily Scholar",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    title: "Daily Scholar",
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: [
      { url: "/icons/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
    shortcut: "/icons/favicon.ico",
  },
  formatDetection: {
    telephone: false,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#0f172a",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-slate-50 min-h-screen`}>
        {/* Navigation */}
        <nav className="bg-white border-b border-slate-200 sticky top-0 z-50">
          <div className="max-w-6xl mx-auto px-4">
            <div className="flex items-center justify-between h-16">
              {/* Logo */}
              <Link href="/" className="flex items-center gap-2">
                <span className="text-2xl">📚</span>
                <span className="font-bold text-xl text-slate-900">Daily Scholar</span>
              </Link>

              {/* Desktop navigation links — collapsed to the MobileTabBar at the
                  bottom of the screen on phones (see <MobileTabBar /> below) */}
              <div className="hidden md:flex items-center gap-1">
                <Link
                  href="/"
                  className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-all"
                >
                  Dashboard
                </Link>
                <Link 
                  href="/papers"
                  className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-all flex items-center gap-1"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                  </svg>
                  Papers
                </Link>
                <Link 
                  href="/topics"
                  className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-all flex items-center gap-1"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                  </svg>
                  Topics
                </Link>
                <Link
                  href="/quiz"
                  className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-all flex items-center gap-1"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                  </svg>
                  Quizzes
                </Link>
                <Link
                  data-tour="settings"
                  href="/settings/scope"
                  className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-all flex items-center gap-1"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  Settings
                </Link>
                <a
                  href={`${API_BASE}/docs`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-2 px-3 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 border border-slate-200 hover:border-slate-300 rounded-lg transition-all"
                >
                  API Docs
                </a>
                <UserMenu />
              </div>
            </div>
          </div>
        </nav>

        {/* Main Content — pb-24 reserves room for the fixed MobileTabBar on
            phones; desktop falls back to normal py-8 spacing */}
        <main className="max-w-6xl mx-auto px-4 py-8 pb-24 md:pb-8">
          {children}
        </main>

        {/* Footer — hidden on mobile because the bottom tab bar would overlap it */}
        <footer className="hidden md:block border-t border-slate-200 mt-auto py-6">
          <div className="max-w-6xl mx-auto px-4 text-center text-sm text-slate-500">
            Daily Scholar — Learn something new every day 🎓
          </div>
        </footer>

        {/* Mobile-only fixed bottom tab bar with Settings/API Docs in a sheet */}
        <MobileTabBar />

        {/* Global 401 banner — only fires once CF Access JWT verification is on */}
        <AuthBoundary />

        {/* Phase E: redirect logged-in unonboarded users to /onboarding */}
        <OnboardingGuard />

        {/* Phase E: redirect onboarded users with no active scope to the picker */}
        <ScopePickerGuard />

        {/* Phase E follow-up: per-page guided product tours.
            Each component self-gates on user.onboarded + pathname + server-side
            user.tour_state[tour_id] < component's TOUR_VERSION. */}
        <DashboardTour />
        <ScopeTour />
        <TopicsTour />

        {/* PWA install prompt (shows on capable browsers / iOS Safari) */}
        <InstallPrompt />
      </body>
    </html>
  );
}
