import * as Sentry from "@sentry/nextjs";

import { scrub } from "@/lib/sentry-scrub";

/**
 * Error reporting for the server side of Next (Phase 11 step 5).
 *
 * Next calls `register()` once per runtime. Like the Django side, a missing DSN
 * initialises nothing — development and CI need no Sentry account and send nothing,
 * and there is no `if (sentry)` anywhere else in the app.
 */
export async function register() {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;

  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? "development",
    release: process.env.NEXT_PUBLIC_SENTRY_RELEASE,
    tracesSampleRate: Number(process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? 0.1),
    // v11 no longer attaches personal data by default, which is the right default but
    // not a guarantee. `scrub` is the guarantee, and it redacts the same names the
    // Django side does.
    beforeSend: scrub,
  });
}

/**
 * Server-side errors Next catches before they reach a page.
 *
 * Without this, a failure inside a Server Component renders an error page and is never
 * reported — which is exactly the kind that nobody tells you about.
 */
export const onRequestError = Sentry.captureRequestError;
