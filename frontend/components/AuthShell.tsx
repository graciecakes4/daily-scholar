'use client';

/**
 * Shared layout primitives for the auth pages (/login, /signup,
 * /account/*). Lives outside the `app/` tree because Next.js App Router
 * page files can only export `default` + a few framework-recognized
 * names; re-exporting helpers from a page would fail the build.
 */

import React from 'react';

export function AuthShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="max-w-md mx-auto mt-12">
      <h1 className="text-2xl font-bold text-slate-900 mb-6 text-center">{title}</h1>
      <div className="bg-white border border-slate-200 rounded-lg p-6 shadow-sm">
        {children}
      </div>
    </div>
  );
}

export function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
    </div>
  );
}
