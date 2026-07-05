import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import InstallPrompt from "@/components/InstallPrompt";
import AuthBoundary from "@/components/AuthBoundary";
import DashboardTour from "@/components/DashboardTour";
import MobileTabBar from "@/components/MobileTabBar";
import OnboardingGuard from "@/components/OnboardingGuard";
import ScopePickerGuard from "@/components/ScopePickerGuard";
import ScopeTour from "@/components/ScopeTour";
import ThemeProvider, { THEME_STORAGE_KEY, THEME_COLORS } from "@/components/ThemeProvider";
import TopicsTour from "@/components/TopicsTour";
import Sidebar from "@/components/Sidebar";

const inter = Inter({ subsets: ["latin"] });

// Phase 5 / fd3 — blocking inline script, applied before first paint so a
// returning user's saved theme/font-size never flashes editorial-then-
// their-theme. Reads the cache ThemeProvider maintains in localStorage;
// falls back to the "editorial"/"medium" defaults (which already match
// globals.css :root, so even a cold cache renders correctly). Prefers
// resolved_theme/resolved_accent when present so a user on "Random"
// still gets this week's actual pick pre-painted instead of a generic
// fallback; a stale cache (e.g. crossing into a new ISO week) briefly
// shows last week's pick until ThemeProvider's effect re-fetches and
// re-caches, same tradeoff as any other cross-device settings change.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var raw = localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
    var s = raw ? JSON.parse(raw) : null;
    var theme = (s && (s.resolved_theme || s.theme)) || 'editorial';
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-font-size', (s && s.font_size) || 'medium');
    document.documentElement.setAttribute('data-reading-font', (s && s.reading_font) || 'theme');
    var accent = s && (s.resolved_accent || s.accent);
    if (accent) {
      document.documentElement.setAttribute('data-accent', accent);
    }
    var colors = ${JSON.stringify(THEME_COLORS)};
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', colors[theme] || colors.editorial);
  } catch (e) {}
})();
`;

// PWA-aware metadata. The viewport export drives the <meta name="theme-color">
// so the browser chrome (iOS Safari status bar, Android task switcher card)
// matches the app's warm paper background.
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
  // matches --paper so the browser chrome flows into the page background
  themeColor: "#F2EBDD",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className={`${inter.className} min-h-screen text-ink`}>
        {/* app-shell wraps the two-column grid above the paper-noise overlay
            (see body::before in globals.css). On md+ the Sidebar takes 280px
            and the main column flexes; on mobile the sidebar hides and the
            MobileTabBar at the bottom handles navigation. */}
        <div className="app-shell flex min-h-screen">
          <Sidebar />
          {/* main column — paddingTop carries the iOS safe-area inset so the
              header drops below the Dynamic Island / notch. pb-24 reserves
              room for the fixed MobileTabBar on phones. */}
          <main
            className="flex-1 min-w-0 px-5 py-8 pb-24 md:px-14 md:py-12 md:pb-12"
            style={{ paddingTop: 'calc(env(safe-area-inset-top) + 2rem)' }}
          >
            <div className="mx-auto w-full max-w-[1080px]">
              {children}
            </div>
          </main>
        </div>

        {/* Mobile-only fixed bottom tab bar with Settings/API Docs in a sheet */}
        <MobileTabBar />

        {/* Phase 5 / fd3: applies the user's saved theme + font size */}
        <ThemeProvider />

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
