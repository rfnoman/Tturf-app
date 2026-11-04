"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@clerk/nextjs";

import { API_BASE_URL } from "@/lib/api/config";

/**
 * Keeps the app in step with the server over SSE (DECISIONS D54).
 *
 * Read with `fetch` streaming rather than `EventSource`, because `EventSource` cannot
 * send an Authorization header and a token in the query string ends up in every access
 * log. A stream that will not open is not an error: the bell already polls, so the
 * worst case is a slower notification.
 */
export function LiveNotifications() {
  const { getToken, isSignedIn } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isSignedIn) return;

    const controller = new AbortController();
    let cancelled = false;

    (async () => {
      try {
        const token = await getToken();
        if (!token) return;

        const response = await fetch(`${API_BASE_URL}/api/v1/me/notifications/stream`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!response.ok || !response.body) return;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!cancelled) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          // SSE frames are separated by a blank line.
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";

          for (const frame of frames) {
            if (!frame.includes("event: notification")) continue;
            // Re-render whatever the player is looking at; the server is the source of
            // truth for what changed, and the payload is only a hint that it did.
            router.refresh();
          }
        }
      } catch {
        // Aborted, offline, or no stream available: polling carries on regardless.
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [getToken, isSignedIn, router]);

  return null;
}
