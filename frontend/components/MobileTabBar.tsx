'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';
import { API_BASE, resetTour } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

// keep in sync with KNOWN_TOUR_IDS on the backend and the desktop sidebar's
// TOUR_CHOICES — single source of truth lives in the backend frozenset
type TourChoice = { id: 'dashboard' | 'scope' | 'topics'; label: string; fire_on_path: string };
const TOUR_CHOICES: TourChoice[] = [
  { id: 'dashboard', label: 'Dashboard tour', fire_on_path: '/' },
  { id: 'scope', label: 'Scope library tour', fire_on_path: '/settings/scope' },
  { id: 'topics', label: 'Topics tour', fire_on_path: '/topics' },
];

// inline SVGs kept here so the tab bar is fully self-contained and the layout
// can stay a server component
const HomeIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M3 12l9-9 9 9" />
    <path d="M5 10v10h14V10" />
  </svg>
);

const PapersIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
  </svg>
);

const TopicsIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
  </svg>
);

const QuizIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
  </svg>
);

const MoreIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <circle cx="5" cy="12" r="1" />
    <circle cx="12" cy="12" r="1" />
    <circle cx="19" cy="12" r="1" />
  </svg>
);

const LibraryIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M4 6h16M4 12h16M4 18h10" />
  </svg>
);

const SearchIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <circle cx="11" cy="11" r="7" />
    <path d="M21 21l-4.3-4.3" />
  </svg>
);

const PlusIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M12 5v14M5 12h14" />
  </svg>
);

const InboxIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M3 8l9 6 9-6M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
  </svg>
);

const ProfileIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21a8 8 0 0116 0" />
  </svg>
);

const NotificationsIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
  </svg>
);

const PlayIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M8 12l2 2 6-6M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const ExternalIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
  </svg>
);

const CloseIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <line x1="6" y1="6" x2="18" y2="18" />
    <line x1="18" y1="6" x2="6" y2="18" />
  </svg>
);

const ChevronLeftIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <path d="M15 19l-7-7 7-7" />
  </svg>
);

type Tab = {
  href: string;
  label: string;
  match: (path: string) => boolean;
  icon: ReactNode;
};

// tab definitions are kept here so future topics/courses-agnostic refactors can
// swap the tab list by editing one array
const TABS: Tab[] = [
  { href: '/', label: 'Today', icon: <HomeIcon />, match: (p) => p === '/' },
  { href: '/papers', label: 'Papers', icon: <PapersIcon />, match: (p) => p.startsWith('/papers') },
  { href: '/topics', label: 'Topics', icon: <TopicsIcon />, match: (p) => p.startsWith('/topics') },
  { href: '/quiz', label: 'Quizzes', icon: <QuizIcon />, match: (p) => p.startsWith('/quiz') },
];

type SheetGroup = {
  label: string;
  items: SheetItem[];
};

type SheetItem = {
  label: string;
  icon: ReactNode;
} & ({ href: string; external?: boolean; onClick?: undefined } | { onClick: () => void; href?: undefined });

export default function MobileTabBar() {
  const pathname = usePathname() || '/';
  const router = useRouter();
  const { refresh } = useAuth();
  const [moreOpen, setMoreOpen] = useState(false);
  // 'menu' = default Help list; 'picker' = swap in the three tour choices
  // in-place. busy holds the id mid-await for a visible loading hint.
  const [helpView, setHelpView] = useState<'menu' | 'picker'>('menu');
  const [busyTour, setBusyTour] = useState<string | null>(null);

  // any route not claimed by a tab (e.g., /settings/*) shows as "More" active
  const activeTabIdx = TABS.findIndex((t) => t.match(pathname));
  const moreActive = activeTabIdx === -1;

  // close sheet on route change; also reset the help view so reopening
  // the sheet always starts on the default list
  useEffect(() => {
    setMoreOpen(false);
    setHelpView('menu');
  }, [pathname]);

  // escape key closes the sheet
  useEffect(() => {
    if (!moreOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMoreOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [moreOpen]);

  async function replayTour(choice: TourChoice) {
    if (busyTour) return;
    setBusyTour(choice.id);
    try {
      await resetTour(choice.id);
      await refresh();
      // sheet closes automatically on the resulting pathname change
      router.push(choice.fire_on_path);
    } catch (e) {
      console.warn(`failed to replay ${choice.id} tour`, e);
    } finally {
      setBusyTour(null);
    }
  }

  // mirrors the desktop sidebar IA so mobile/desktop stay legible together.
  // the Help group's items array swaps based on helpView — picker mode
  // surfaces a small back row + the three tour choices.
  const helpItems: SheetItem[] = helpView === 'menu'
    ? [
        { onClick: () => setHelpView('picker'), label: 'Replay tutorials', icon: <PlayIcon /> },
        { href: `${API_BASE}/docs`, external: true, label: 'API docs', icon: <ExternalIcon /> },
      ]
    : [
        { onClick: () => { if (!busyTour) setHelpView('menu'); }, label: 'Back', icon: <ChevronLeftIcon /> },
        ...TOUR_CHOICES.map((choice) => ({
          onClick: () => replayTour(choice),
          label: choice.label,
          icon: <PlayIcon />,
        })),
      ];

  const groups: SheetGroup[] = [
    {
      label: 'Scope',
      items: [
        { href: '/settings/scope', label: 'Library', icon: <LibraryIcon /> },
        { href: '/scopes/browse', label: 'Browse public', icon: <SearchIcon /> },
        { href: '/scopes/picker', label: 'New scope', icon: <PlusIcon /> },
        { href: '/scopes/requests', label: 'Access requests', icon: <InboxIcon /> },
      ],
    },
    {
      label: 'Account',
      items: [
        { href: '/settings/account', label: 'Profile & password', icon: <ProfileIcon /> },
        { href: '/settings/notifications', label: 'Notifications', icon: <NotificationsIcon /> },
      ],
    },
    {
      label: 'Help',
      items: helpItems,
    },
  ];

  return (
    <>
      <nav
        aria-label="Primary"
        className="md:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-rule bg-paper-2/95 backdrop-blur"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <div className="grid grid-cols-5 h-16">
          {TABS.map((tab, idx) => {
            const active = idx === activeTabIdx;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={active ? 'page' : undefined}
                className={`relative flex flex-col items-center justify-center gap-1 text-[10px] font-medium transition-colors ${
                  active ? 'text-ink' : 'text-muted hover:text-ink-2'
                }`}
              >
                {active && (
                  <span className="absolute top-1.5 h-0.5 w-6 rounded-full bg-gold" aria-hidden />
                )}
                {tab.icon}
                <span className={active ? 'font-semibold' : ''}>{tab.label}</span>
              </Link>
            );
          })}
          <button
            type="button"
            onClick={() => setMoreOpen(true)}
            aria-haspopup="dialog"
            aria-expanded={moreOpen}
            aria-current={moreActive ? 'page' : undefined}
            className={`relative flex flex-col items-center justify-center gap-1 text-[10px] font-medium transition-colors ${
              moreActive ? 'text-ink' : 'text-muted hover:text-ink-2'
            }`}
          >
            {moreActive && (
              <span className="absolute top-1.5 h-0.5 w-6 rounded-full bg-gold" aria-hidden />
            )}
            <MoreIcon />
            <span className={moreActive ? 'font-semibold' : ''}>More</span>
          </button>
        </div>
      </nav>

      {moreOpen && (
        <div className="md:hidden fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="More menu">
          <button
            type="button"
            aria-label="Close menu"
            onClick={() => setMoreOpen(false)}
            className="absolute inset-0 bg-ink/45 animate-in"
          />
          <div
            className="absolute bottom-0 left-0 right-0 rounded-t-2xl border-t border-rule bg-paper-2 px-4 pt-3 shadow-2xl animate-in"
            style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 1.25rem)' }}
          >
            <div className="mx-auto w-10 h-1.5 rounded-full bg-rule mb-3" aria-hidden />
            <div className="mb-2 flex items-center justify-between">
              <h2 className="font-serif text-[18px] font-semibold tracking-tight text-ink">More</h2>
              <button
                type="button"
                onClick={() => setMoreOpen(false)}
                aria-label="Close"
                className="-m-1 p-1 text-muted hover:text-ink"
              >
                <CloseIcon />
              </button>
            </div>
            <div className="max-h-[70vh] overflow-y-auto">
              {groups.map((group) => (
                <div key={group.label} className="mb-3 last:mb-0">
                  <div className="mb-1 mt-1 flex items-center gap-2 font-serif text-[11px] font-medium italic uppercase tracking-[0.16em] text-muted">
                    <span>{group.label}</span>
                    <span aria-hidden className="h-px flex-1 bg-rule" />
                  </div>
                  {group.items.map((item) => {
                    const isActive = 'href' in item && item.href !== undefined && !item.external
                      ? pathname === item.href || pathname.startsWith(item.href + '/')
                      : false;
                    const baseCls = `flex items-center gap-3 rounded-lg px-3 py-2.5 text-[14px] ${
                      isActive ? 'bg-paper-3 font-semibold text-ink' : 'text-ink-2 hover:bg-paper-3'
                    }`;
                    if ('onClick' in item && item.onClick) {
                      // tour-picker rows: match by label so we can show
                      // a busy hint and disable while the per-tour reset
                      // round-trips through the backend
                      const matchingTour = TOUR_CHOICES.find((c) => c.label === item.label);
                      const loading = matchingTour && busyTour === matchingTour.id;
                      const disabled = !!busyTour && (matchingTour !== undefined || item.label === 'Back');
                      return (
                        <button
                          key={item.label}
                          type="button"
                          onClick={item.onClick}
                          disabled={disabled}
                          aria-busy={loading || undefined}
                          className={`${baseCls} w-full text-left disabled:cursor-not-allowed ${loading ? 'bg-paper-3 text-ink' : ''}`}
                        >
                          <span className={loading ? 'text-gold-dark animate-pulse' : 'text-muted'}>{item.icon}</span>
                          <span>{item.label}</span>
                          {loading && (
                            <span className="ml-auto font-mono text-[10px] uppercase tracking-wider text-gold-dark">loading</span>
                          )}
                        </button>
                      );
                    }
                    if (item.external && item.href) {
                      return (
                        <a
                          key={item.label}
                          href={item.href}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={() => setMoreOpen(false)}
                          className={baseCls}
                        >
                          <span className="text-muted">{item.icon}</span>
                          <span>{item.label}</span>
                          <span className="ml-auto font-mono text-[10px] uppercase tracking-wider text-muted">new tab</span>
                        </a>
                      );
                    }
                    return (
                      <Link
                        key={item.label}
                        href={item.href!}
                        onClick={() => setMoreOpen(false)}
                        className={baseCls}
                      >
                        <span className={isActive ? 'text-gold-dark' : 'text-muted'}>{item.icon}</span>
                        <span>{item.label}</span>
                      </Link>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
