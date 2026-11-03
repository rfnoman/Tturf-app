import { clerkMiddleware } from "@clerk/nextjs/server";

/**
 * Next.js 16 renamed `middleware.ts` to `proxy.ts` (Node runtime only, no `edge`).
 *
 * This runs bare: it attaches the Clerk session to the request and nothing else.
 * Route protection happens at the resource — `await auth.protect()` in the (player),
 * (owner) and (admin) layouts — because Clerk deprecated `createRouteMatcher` after the
 * 2025 middleware-bypass disclosures and now recommends gating as close to the data as
 * possible (DECISIONS D12).
 *
 * Locale needs no middleware here: the choice lives in a cookie, not the URL (D13).
 */
export default clerkMiddleware();

export const config = {
  matcher: [
    // Everything except Next internals and static files.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
    // Clerk's own handshake/bridge routes.
    "/__clerk/(.*)",
  ],
};
