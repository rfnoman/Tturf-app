import * as Sentry from "@sentry/nextjs";

import { scrub } from "@/lib/sentry-scrub";

/**
 * Error reporting in the browser (Phase 11 step 5).
 *
 * This is the half that matters most: a booking that fails on one player's phone, on a
 * connection that dropped halfway, is invisible from the server. Nothing is sent
 * without a DSN.
 */
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? "development",
    release: process.env.NEXT_PUBLIC_SENTRY_RELEASE,
    tracesSampleRate: Number(process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? 0.1),
    beforeSend: scrub,
    // Session replay is deliberately not enabled: it would record players' own screens,
    // including their phone numbers and delivery addresses, to a third party.
  });
}

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
