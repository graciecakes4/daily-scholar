'use client';

/**
 * Visual password strength hint — weak / fair / good / strong.
 *
 * Scoring is a small heuristic (no extra deps). Length tiers dominate
 * (8/12/16 chars unlock a tier each) and character-class diversity
 * (lowercase / uppercase / digit / symbol) adds bumps. Not as good
 * as zxcvbn but fits in one file and doesn't add 400KB to the bundle.
 *
 * Useful as a hint, not a gate — backend still enforces the actual
 * minimum-length rule (8 chars via passlib + pydantic Field validation).
 */

import React from 'react';

export type Strength = 'empty' | 'weak' | 'fair' | 'good' | 'strong';

interface Props {
  password: string;
  /** Hide entirely when the field is empty. Defaults to true. */
  hideWhenEmpty?: boolean;
}

const COPY: Record<Strength, { label: string; hint: string; barCls: string; textCls: string; widthCls: string }> = {
  empty:  { label: '',         hint: '',                                                                    barCls: 'bg-slate-200', textCls: 'text-slate-500', widthCls: 'w-0' },
  weak:   { label: 'Weak',     hint: 'Try at least 8 characters with a mix of upper/lower and digits.',     barCls: 'bg-rose-500',  textCls: 'text-rose-700',  widthCls: 'w-1/4' },
  fair:   { label: 'Fair',     hint: 'Longer is better. Add a symbol or another character class.',          barCls: 'bg-amber-500', textCls: 'text-amber-700', widthCls: 'w-2/4' },
  good:   { label: 'Good',     hint: 'Good. A few more characters or a symbol would make it stronger.',    barCls: 'bg-sky-500',   textCls: 'text-sky-700',   widthCls: 'w-3/4' },
  strong: { label: 'Strong',   hint: 'Strong. Hard to brute-force.',                                       barCls: 'bg-emerald-500', textCls: 'text-emerald-700', widthCls: 'w-full' },
};

export function scorePassword(pw: string): Strength {
  if (!pw) return 'empty';
  const classes =
    (/[a-z]/.test(pw) ? 1 : 0) +
    (/[A-Z]/.test(pw) ? 1 : 0) +
    (/[0-9]/.test(pw) ? 1 : 0) +
    (/[^A-Za-z0-9]/.test(pw) ? 1 : 0);
  const len = pw.length;

  // hard cutoffs first — anything under 8 chars is weak no matter
  // how diverse, because backend rejects sub-8 anyway
  if (len < 8) return 'weak';

  // tiered: length sets the floor, class diversity nudges up
  if (len >= 16 && classes >= 3) return 'strong';
  if (len >= 12 && classes >= 2) return 'good';
  if (len >= 8 && classes >= 2) return 'fair';
  return 'weak';
}

export default function PasswordStrength({ password, hideWhenEmpty = true }: Props) {
  const strength = scorePassword(password);
  if (strength === 'empty' && hideWhenEmpty) return null;

  const copy = COPY[strength];

  return (
    <div className="space-y-1" aria-live="polite">
      <div className="h-1 w-full bg-slate-100 rounded overflow-hidden">
        <div
          className={`h-full transition-all duration-200 ${copy.barCls} ${copy.widthCls}`}
          role="progressbar"
          aria-valuenow={
            { empty: 0, weak: 25, fair: 50, good: 75, strong: 100 }[strength]
          }
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Password strength: ${copy.label || 'empty'}`}
        />
      </div>
      {strength !== 'empty' && (
        <div className="flex items-baseline justify-between text-xs">
          <span className={`font-medium ${copy.textCls}`}>{copy.label}</span>
          <span className="text-slate-500">{copy.hint}</span>
        </div>
      )}
    </div>
  );
}
