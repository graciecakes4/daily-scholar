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
