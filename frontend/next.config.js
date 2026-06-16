/**
 * Next.js + @serwist/next configuration.
 *
 * Service worker is built from `app/sw.ts` into `public/sw.js` at build time.
 * The dev server registers the SW too, but with --no-cache so reloads pick up
 * source changes immediately.
 */

const withSerwist = require("@serwist/next").default({
  swSrc: "app/sw.ts",
  swDest: "public/sw.js",
  // Don't register the SW in dev unless explicitly enabled —
  // hot reload + SW caching is a confusing combo for first-time setup.
  disable: process.env.NODE_ENV === "development",
  reloadOnOnline: true,
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
};

module.exports = withSerwist(nextConfig);
