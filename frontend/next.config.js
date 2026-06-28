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
  // produce a self-contained Next.js server in `.next/standalone` for the
  // Docker runtime stage (no full node_modules in the final image)
  output: "standalone",

  // Same-origin proxy for the FastAPI backend.
  //
  // Browser code calls relative `/api/*` URLs (see lib/api.ts API_BASE).
  // This rewrite forwards them to the backend over the private network,
  // so the browser never crosses an origin boundary. Eliminates the
  // CORS allowlist + cross-subdomain CSRF cookie class of bugs.
  //
  // BACKEND_INTERNAL_URL precedence:
  //   - Railway prod   → http://backend.railway.internal:8000
  //   - docker-compose → http://backend:8000  (compose-network alias)
  //   - npm run dev    → http://localhost:8000 (fallback below)
  //
  // The env var is read at request time on the standalone Node server,
  // so changing it requires a service restart but not a rebuild.
  async rewrites() {
    const backend =
      process.env.BACKEND_INTERNAL_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend.replace(/\/$/, "")}/:path*`,
      },
    ];
  },
};

module.exports = withSerwist(nextConfig);
