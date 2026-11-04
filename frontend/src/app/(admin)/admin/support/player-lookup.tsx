"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { useApiClient } from "@/lib/api/use-api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { When } from "@/components/ui/when";

type Found = {
  id: string;
  name: string;
  email: string;
  phone: string;
  player_profile_id: string | null;
  is_platform_admin: boolean;
  is_active: boolean;
  created_at: string;
};

export function PlayerLookup() {
  const t = useTranslations("support");
  const api = useApiClient();
  const [query, setQuery] = useState("");
  // Results are stored with the query that produced them, so what is on screen can be
  // *derived* rather than cleared by an effect — a stale list never shows under a
  // query it does not belong to, and no state is set synchronously during render.
  const [found, setFound] = useState<{ query: string; rows: Found[] }>({ query: "", rows: [] });

  // Three characters is the server's floor too: anything shorter would return most of
  // the directory, which is not a lookup.
  const term = query.trim();
  const ready = term.length >= 3;
  const results = found.query === term ? found.rows : [];
  const searching = ready && found.query !== term;

  useEffect(() => {
    if (term.length < 3) return;

    let cancelled = false;
    const timer = setTimeout(async () => {
      const { data } = await api.GET("/api/v1/admin/players", {
        params: { query: { q: term } },
      });
      if (!cancelled) setFound({ query: term, rows: (data ?? []) as Found[] });
    }, 250);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [api, term]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="lookup">{t("search")}</Label>
        <Input
          id="lookup"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("searchPlaceholder")}
          autoComplete="off"
        />
      </div>

      {searching && <p className="text-muted-foreground text-sm">{t("searching")}</p>}

      {!searching && ready && results.length === 0 && (
        <p className="text-muted-foreground text-sm">{t("nobody")}</p>
      )}

      {results.length > 0 && (
        <ul className="flex flex-col gap-2">
          {results.map((person) => (
            <li key={person.id} className="flex flex-col gap-1 rounded-lg border p-3 text-sm">
              <span className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium">{person.name}</span>
                <span className="text-muted-foreground text-xs">
                  {t("joined")} <When at={person.created_at} style="dayMonthYear" className="" />
                </span>
              </span>
              <span className="text-muted-foreground">{person.email}</span>
              {person.phone && <span className="text-muted-foreground">{person.phone}</span>}
              <span className="flex flex-wrap gap-2 text-xs">
                {!person.is_active && (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 dark:bg-amber-900">
                    {t("inactive")}
                  </span>
                )}
                {person.is_platform_admin && (
                  <span className="bg-muted rounded px-1.5 py-0.5">{t("admin")}</span>
                )}
                {person.player_profile_id && (
                  <Link
                    href={`/players/${person.player_profile_id}`}
                    className="text-primary hover:underline"
                  >
                    {t("viewProfile")}
                  </Link>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
