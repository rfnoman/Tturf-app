"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Bell } from "lucide-react";

import type { Notification } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/** How often the bell re-checks. Real-time delivery arrives with web push in Phase 09. */
const POLL_MS = 30_000;

/**
 * The notification centre (DOMAIN §11).
 *
 * Polls the unread count rather than the full list — the badge is what changes most
 * often, and it is a single `COUNT(*)` on an index. The list is only fetched when the
 * reader actually opens the dropdown.
 */
export function NotificationBell() {
  const t = useTranslations("notifications");
  const api = useApiClient();
  const router = useRouter();

  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);

  const refreshCount = useCallback(async () => {
    const { data } = await api.GET("/api/v1/me/notifications/unread-count");
    setUnread(data?.unread ?? 0);
  }, [api]);

  useEffect(() => {
    let cancelled = false;
    // Deferred by a tick so the effect body itself never calls setState.
    const timer = setTimeout(() => {
      if (!cancelled) void refreshCount();
    }, 0);
    const interval = setInterval(() => {
      if (!cancelled) void refreshCount();
    }, POLL_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
      clearInterval(interval);
    };
  }, [refreshCount]);

  async function load() {
    setLoading(true);
    const { data } = await api.GET("/api/v1/me/notifications", {
      params: { query: { page_size: 8 } },
    });
    setItems(data?.results ?? []);
    setLoading(false);
  }

  async function markAllRead() {
    await api.POST("/api/v1/me/notifications/read", { body: {} as never });
    await refreshCount();
    await load();
    // Server components may be rendering counts of their own.
    router.refresh();
  }

  return (
    <DropdownMenu
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) void load();
      }}
    >
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("ariaLabel", { count: unread })}>
          <span className="relative inline-flex">
            <Bell aria-hidden />
            {unread > 0 && (
              <span
                aria-hidden
                className="bg-destructive text-destructive-foreground absolute -top-1.5 -right-2 min-w-4 rounded-full px-1 text-[0.625rem] leading-4 font-semibold"
              >
                {unread > 9 ? "9+" : unread}
              </span>
            )}
          </span>
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
          <span className="text-sm font-semibold">{t("heading")}</span>
          {unread > 0 && (
            <Button size="xs" variant="ghost" onClick={markAllRead}>
              {t("markAllRead")}
            </Button>
          )}
        </div>

        <ul className="max-h-96 overflow-y-auto">
          {loading && items.length === 0 ? (
            <li className="text-muted-foreground px-3 py-6 text-center text-sm">{t("loading")}</li>
          ) : items.length === 0 ? (
            <li className="text-muted-foreground px-3 py-6 text-center text-sm">{t("empty")}</li>
          ) : (
            items.map((item) => {
              const body = (
                <>
                  <span className="flex items-start gap-2">
                    {!item.is_read && (
                      <span
                        aria-hidden
                        className="bg-primary mt-1.5 size-1.5 shrink-0 rounded-full"
                      />
                    )}
                    <span className={item.is_read ? "text-muted-foreground" : "font-medium"}>
                      {item.title}
                    </span>
                  </span>
                  {item.body && (
                    <span className="text-muted-foreground mt-0.5 block text-xs">{item.body}</span>
                  )}
                </>
              );

              return (
                <li key={item.id} className="border-b last:border-b-0">
                  {item.url ? (
                    <Link
                      href={item.url}
                      className="hover:bg-muted/60 block px-3 py-2 text-sm"
                      onClick={() => setOpen(false)}
                    >
                      {body}
                    </Link>
                  ) : (
                    <div className="px-3 py-2 text-sm">{body}</div>
                  )}
                </li>
              );
            })
          )}
        </ul>

        <div className="border-t px-3 py-2">
          <Link
            href="/notifications"
            className="text-muted-foreground text-xs underline"
            onClick={() => setOpen(false)}
          >
            {t("seeAll")}
          </Link>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
