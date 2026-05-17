# syntax=docker/dockerfile:1.7
# CPIA web — Next.js 14 standalone container

# ---------- deps ----------
FROM node:20-alpine AS deps
WORKDIR /app/web
RUN apk add --no-cache libc6-compat
COPY web/package.json web/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# ---------- builder ----------
FROM node:20-alpine AS builder
WORKDIR /app/web
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/web/node_modules ./node_modules
COPY web/ ./
RUN npm run build

# ---------- runner ----------
FROM node:20-alpine AS runner
WORKDIR /app/web
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=5535 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

# Next.js standalone output
COPY --from=builder --chown=nextjs:nodejs /app/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/web/.next/static ./.next/static

USER nextjs

EXPOSE 5535

CMD ["node", "server.js"]
