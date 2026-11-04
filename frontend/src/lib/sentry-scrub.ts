import type { ErrorEvent } from "@sentry/nextjs";

/**
 * Strip anything credential-shaped before an event leaves the browser or the server.
 *
 * `@sentry/nextjs` v11 removed `sendDefaultPii` — personal data is no longer attached
 * by default, which is the right default but is not the same as a guarantee. This is
 * the guarantee, and it mirrors `apps/core/observability.py` so both halves of the app
 * redact the same names. `store_passwd` in particular is SSLCommerz's spelling (D59),
 * not something a generic denylist would know to look for.
 */
const SENSITIVE = new Set([
  "store_passwd",
  "store_id",
  "card_no",
  "verify_sign",
  "verify_key",
  "password",
  "token",
  "authorization",
  "phone",
  "email",
]);

function clean(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(clean);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [
        key,
        SENSITIVE.has(key.toLowerCase()) ? "[redacted]" : clean(item),
      ]),
    );
  }
  return value;
}

export function scrub(event: ErrorEvent): ErrorEvent {
  return clean(event) as ErrorEvent;
}
