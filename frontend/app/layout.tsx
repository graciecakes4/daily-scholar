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
import TopicsTour from "@/components/TopicsTour";
import Sidebar from "@/components/Sidebar";

const inter = Inter({ subsets: ["latin"] });

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
