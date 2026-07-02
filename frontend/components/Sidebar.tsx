'use client';

/**
 * Sidebar — the persistent left rail (option b · editorial sidebar).
 *
 * 280px wide, hidden under md: (mobile falls back to MobileTabBar).
 * Mounts the ActiveScopeChip at the top, then named groups mirroring the
 * settings IA (Read · Scope · Notifications · Account · Tutorials ·
 * Admin), and a user chip in the footer. This nav is the single source
 * of truth for cross-section navigation — individual settings pages no
 * longer carry their own "related page" link clusters.
 *
 * Active state is computed from usePathname() — matches the deepest
 * prefix so /papers/123 still highlights "Papers".
 */

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { API_BASE } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';
import ActiveScopeChip from './ActiveScopeChip';

// inline icon components — kept here so the sidebar stays self-contained
// and svg paths match the mockup exactly
type IconProps = { className?: string };

const HomeIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l9-9 9 9M5 10v10h14V10" />
  </svg>
);

const PapersIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13" />
  </svg>
);

const TopicsIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
  </svg>
);

const QuizIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
  </svg>
);

const LibraryIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h10" />
  </svg>
);

const SearchIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <circle cx="11" cy="11" r="7" />
    <path strokeLinecap="round" d="M21 21l-4.3-4.3" />
  </svg>
);

const PlusIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 5v14M5 12h14" />
  </svg>
);

const InboxIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l9 6 9-6M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
  </svg>
);

const ProfileIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <circle cx="12" cy="8" r="4" />
    <path strokeLinecap="round" d="M4 21a8 8 0 0116 0" />
  </svg>
);

const BellIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
  </svg>
);

const PlayIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M8 12l2 2 6-6M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const ExternalIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M10 20H4a1 1 0 01-1-1V5a1 1 0 011-1h6m4 0h6a1 1 0 011 1v14a1 1 0 01-1 1h-6M9 3v18M15 3v18" />
  </svg>
);

const LogoutIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
  </svg>
);

const KeyIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
  </svg>
);

const AtIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <circle cx="12" cy="12" r="4" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M16 12v1.5a2.5 2.5 0 005 0V12a9 9 0 10-3.5 7.14" />
  </svg>
);

const ShieldIcon = ({ className }: IconProps) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" />
  </svg>
);

// hides the sidebar on the bare auth pages — they own the full viewport
const HIDE_PATH_PREFIXES = ['/login', '/signup', '/account/'];

type NavItem = {
  href: string;
  label: string;
  icon: ReactNode;
  isActive: (path: string) => boolean;
  badge?: ReactNode;
  dataTour?: string;
};

function isExactRoute(target: string) {
  return (path: string) => path === target;
}

function isRoutePrefix(target: string) {
  return (path: string) => path === target || path.startsWith(target + '/');
}

const READ_ITEMS: NavItem[] = [
  { href: '/', label: 'Dashboard', icon: <HomeIcon className="h-4 w-4" />, isActive: isExactRoute('/') },
  { href: '/papers', label: 'Papers', icon: <PapersIcon className="h-4 w-4" />, isActive: isRoutePrefix('/papers') },
  { href: '/topics', label: 'Topics', icon: <TopicsIcon className="h-4 w-4" />, isActive: isRoutePrefix('/topics') },
  { href: '/quiz', label: 'Quizzes', icon: <QuizIcon className="h-4 w-4" />, isActive: isRoutePrefix('/quiz') },
];

const SCOPE_ITEMS: NavItem[] = [
  { href: '/settings/scope/library', label: 'My scopes', icon: <LibraryIcon className="h-4 w-4" />, isActive: isRoutePrefix('/settings/scope/library'), dataTour: 'settings' },
  { href: '/settings/scope/browse', label: 'Browse public', icon: <SearchIcon className="h-4 w-4" />, isActive: isRoutePrefix('/settings/scope/browse') },
  { href: '/settings/scope/requests', label: 'Access requests', icon: <InboxIcon className="h-4 w-4" />, isActive: isRoutePrefix('/settings/scope/requests') },
  { href: '/settings/scope/new', label: 'New scope', icon: <PlusIcon className="h-4 w-4" />, isActive: isRoutePrefix('/settings/scope/new') },
];

const NOTIFICATIONS_ITEMS: NavItem[] = [
  { href: '/settings/notifications', label: 'Notifications', icon: <BellIcon className="h-4 w-4" />, isActive: isRoutePrefix('/settings/notifications') },
];

const ACCOUNT_ITEMS: NavItem[] = [
  { href: '/settings/account/profile', label: 'Profile', icon: <ProfileIcon className="h-4 w-4" />, isActive: isRoutePrefix('/settings/account/profile') },
  { href: '/settings/account/password', label: 'Password', icon: <KeyIcon className="h-4 w-4" />, isActive: isRoutePrefix('/settings/account/password') },
  { href: '/settings/account/username', label: 'Username', icon: <AtIcon className="h-4 w-4" />, isActive: isRoutePrefix('/settings/account/username') },
];

const TUTORIALS_ITEMS: NavItem[] = [
  { href: '/settings/tutorials', label: 'Tutorials', icon: <PlayIcon className="h-4 w-4" />, isActive: isRoutePrefix('/settings/tutorials') },
];

const ADMIN_ITEMS: NavItem[] = [
  { href: '/settings/admin', label: 'Admin', icon: <ShieldIcon className="h-4 w-4" />, isActive: isRoutePrefix('/settings/admin') },
];

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const active = item.isActive(pathname);
  return (
    <Link
      href={item.href}
      data-tour={item.dataTour}
      aria-current={active ? 'page' : undefined}
      className={`group relative flex items-center gap-2.5 rounded-[7px] px-2.5 py-1.5 text-[13.5px] transition-colors ${
        active
          ? 'font-semibold text-ink'
          : 'font-medium text-ink-2 hover:bg-paper-3 hover:text-ink'
      }`}
    >
      {active && (
        // gold ledger bar — sits outside the link padding to align with the rail edge
        <span aria-hidden className="absolute -left-[18px] top-1.5 bottom-1.5 w-[3px] rounded-r bg-gold" />
      )}
      <span className={`${active ? 'text-gold-dark' : 'text-muted group-hover:text-ink'}`}>{item.icon}</span>
      <span className="truncate">{item.label}</span>
      {item.badge}
    </Link>
  );
}

function GroupLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mx-1.5 mb-1.5 mt-0.5 flex items-center gap-2 font-serif text-[11px] font-medium italic uppercase tracking-[0.16em] text-muted">
      <span>{children}</span>
      <span aria-hidden className="h-px flex-1 bg-rule" />
    </div>
  );
}

function getInitials(handle: string, email: string): string {
  const source = handle || email;
  if (!source) return '··';
  // split on common separators, fall back to the first two characters
  const parts = source.split(/[\s._-]+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}

function UserChip() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // dismiss the popover when the user clicks outside it
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    const escHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    window.addEventListener('mousedown', handler);
    window.addEventListener('keydown', escHandler);
    return () => {
      window.removeEventListener('mousedown', handler);
      window.removeEventListener('keydown', escHandler);
    };
  }, [menuOpen]);

  if (loading) {
    return <div className="mx-1 h-12 rounded-lg bg-paper-3/50 animate-pulse" />;
  }

  if (!user) {
    return (
      <Link
        href="/login"
        className="mx-1 flex items-center justify-center rounded-lg border border-rule bg-paper-2 px-3 py-2 text-[13px] font-semibold text-ink hover:bg-paper-3 transition-colors"
      >
        Log in
      </Link>
    );
  }

  const handle = user.user_id !== user.email ? user.user_id : user.email;
  const initials = getInitials(user.user_id, user.email);
  const roleLabel = user.role === 'admin' ? 'Scholar · admin' : 'Scholar';

  async function onLogout() {
    setMenuOpen(false);
    await logout();
    router.push('/login');
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setMenuOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-paper-3 transition-colors"
      >
        <span className="inline-flex h-[30px] w-[30px] flex-none items-center justify-center rounded-full bg-ink text-paper font-serif text-[12px] font-semibold">
          {initials}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-semibold text-ink" title={user.email}>{handle}</span>
          <span className="block truncate text-[11px] text-muted">{roleLabel}</span>
        </span>
        <svg className="h-3.5 w-3.5 flex-none text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {menuOpen && (
        <div
          role="menu"
          className="absolute bottom-full left-0 right-0 mb-2 overflow-hidden rounded-lg border border-rule bg-paper-2 shadow-lg"
        >
          <Link
            href="/settings/account/profile"
            onClick={() => setMenuOpen(false)}
            role="menuitem"
            className="flex items-center gap-2 px-3 py-2 text-[13px] text-ink-2 hover:bg-paper-3"
          >
            <ProfileIcon className="h-4 w-4 text-muted" />
            Profile & account
          </Link>
          <button
            type="button"
            onClick={onLogout}
            role="menuitem"
            className="flex w-full items-center gap-2 border-t border-rule px-3 py-2 text-left text-[13px] text-ink-2 hover:bg-paper-3"
          >
            <LogoutIcon className="h-4 w-4 text-muted" />
            Log out
          </button>
        </div>
      )}
    </div>
  );
}

export default function Sidebar() {
  const pathname = usePathname() || '/';
  const { user } = useAuth();

  if (HIDE_PATH_PREFIXES.some((p) => pathname.startsWith(p))) {
    return null;
  }

  return (
    <aside
      aria-label="Primary"
      className="hidden md:flex sticky top-0 h-screen w-[280px] flex-col overflow-y-auto border-r border-rule bg-paper-2 px-[18px] pt-7 pb-[18px]"
    >
      {/* wordmark — fraunces title with italic accent */}
      <Link href="/" className="mx-1.5 mb-1 flex items-baseline gap-2 no-underline text-ink">
        <span className="font-serif text-[24px] font-semibold leading-none tracking-[-0.02em]" style={{ fontVariationSettings: '"SOFT" 30' }}>
          Daily <em className="italic font-medium text-gold-dark">Scholar</em>
        </span>
      </Link>
      <div className="mx-1.5 mt-1 mb-6 font-serif text-[12px] italic tracking-[0.04em] text-muted">
        A daily reading practice
      </div>

      <ActiveScopeChip />

      <div className="mb-4">
        <GroupLabel>Read</GroupLabel>
        <div className="flex flex-col gap-px">
          {READ_ITEMS.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} />
          ))}
        </div>
      </div>

      <div className="mb-4">
        <GroupLabel>Scope</GroupLabel>
        <div className="flex flex-col gap-px">
          {SCOPE_ITEMS.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} />
          ))}
        </div>
      </div>

      <div className="mb-4">
        <GroupLabel>Notifications</GroupLabel>
        <div className="flex flex-col gap-px">
          {NOTIFICATIONS_ITEMS.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} />
          ))}
        </div>
      </div>

      <div className="mb-4">
        <GroupLabel>Account</GroupLabel>
        <div className="flex flex-col gap-px">
          {ACCOUNT_ITEMS.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} />
          ))}
        </div>
      </div>

      <div className="mb-4">
        <GroupLabel>Tutorials</GroupLabel>
        <div className="flex flex-col gap-px">
          {TUTORIALS_ITEMS.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} />
          ))}
        </div>
      </div>

      {user?.role === 'admin' && (
        <div className="mb-4">
          <GroupLabel>Admin</GroupLabel>
          <div className="flex flex-col gap-px">
            {ADMIN_ITEMS.map((item) => (
              <NavLink key={item.href} item={item} pathname={pathname} />
            ))}
          </div>
        </div>
      )}

      <div className="mt-auto border-t border-rule pt-4">
        <a
          href={`${API_BASE}/docs`}
          target="_blank"
          rel="noopener noreferrer"
          className="mb-2 flex items-center gap-2 px-1 text-[12px] font-medium text-muted hover:text-ink transition-colors"
        >
          <ExternalIcon className="h-3.5 w-3.5" />
          API docs
        </a>
        <UserChip />
      </div>
    </aside>
  );
}
