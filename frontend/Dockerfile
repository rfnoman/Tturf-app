# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# The Next.js server (Phase 11 step 8).
#
# Only needed if the frontend is self-hosted; on Vercel this file is unused. It exists so
# that choice stays reversible — a platform decision should not be welded into the code.
#
# `output: "standalone"` in next.config.ts is what makes the runtime layer small: Next
# traces the modules actually imported and copies only those, instead of shipping
# node_modules.
# ---------------------------------------------------------------------------

FROM node:24-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci


FROM node:24-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# These are inlined into the client bundle at build time, so they are build arguments
# rather than runtime environment. Changing one means rebuilding, which is the honest
# shape of it — pretending otherwise produces a bundle that disagrees with its server.
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_SENTRY_DSN
ARG NEXT_PUBLIC_SENTRY_ENVIRONMENT
ARG NEXT_PUBLIC_SENTRY_RELEASE
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN \
    NEXT_PUBLIC_SENTRY_ENVIRONMENT=$NEXT_PUBLIC_SENTRY_ENVIRONMENT \
    NEXT_PUBLIC_SENTRY_RELEASE=$NEXT_PUBLIC_SENTRY_RELEASE

RUN npm run build


FROM node:24-slim AS runtime
WORKDIR /app

ENV NODE_ENV=production
RUN useradd --create-home --uid 10001 next

COPY --from=builder --chown=next:next /app/.next/standalone ./
COPY --from=builder --chown=next:next /app/.next/static ./.next/static
COPY --from=builder --chown=next:next /app/public ./public

USER next
EXPOSE 3000
CMD ["node", "server.js"]
