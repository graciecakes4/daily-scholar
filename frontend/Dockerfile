# Daily Scholar frontend — Next.js 16 standalone build.
#
# Three stages:
#   deps    : install npm deps (lockfile-faithful)
#   builder : run `next build --webpack` so @serwist/next can run (see README)
#   runner  : copy the standalone server + static assets, run `node server.js`
#
# Build context = frontend/; .dockerignore keeps it small.

# ============================================================
# Stage 1: deps
# ============================================================
FROM node:22-alpine AS deps

WORKDIR /app

# enable corepack so users on different package managers work, but we use npm here
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund


# ============================================================
# Stage 2: builder
# ============================================================
FROM node:22-alpine AS builder

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_API_URL is an OPTIONAL escape hatch. Under the same-origin
# setup (lib/api.ts API_BASE defaults to "/api" and next.config.js
# rewrites /api/* to the backend), the browser bundle doesn't need to
# know the backend's URL at all. Set it only if you want the browser
# to call an external API host directly — uncommon, bypasses the proxy.
ARG NEXT_PUBLIC_API_URL=
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# BACKEND_INTERNAL_URL — where Next.js proxies /api/* requests to.
# Must be set at BUILD time, not runtime: Next.js evaluates the
# rewrites() function in next.config.js during `npm run build` and
# bakes the resolved destination into `.next/routes-manifest.json`.
# Changing this value requires a rebuild.
#
#   Railway prod   → http://backend.railway.internal:8000
#   docker-compose → http://backend:8000
#   plain build    → http://localhost:8000 (default fallback in next.config.js)
ARG BACKEND_INTERNAL_URL=
ENV BACKEND_INTERNAL_URL=${BACKEND_INTERNAL_URL}

ENV NEXT_TELEMETRY_DISABLED=1 \
    SERWIST_SUPPRESS_TURBOPACK_WARNING=1

# build with webpack (serwist hooks webpack; Turbopack isn't supported yet)
RUN npm run build


# ============================================================
# Stage 3: runner
# ============================================================
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# non-root user
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# bring over the standalone server + the static assets it doesn't bundle
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
