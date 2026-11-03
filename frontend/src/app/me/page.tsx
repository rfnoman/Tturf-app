import { auth } from "@clerk/nextjs/server";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";

/**
 * Debug page: proves the whole chain works — Clerk session on the frontend, token
 * attached by the typed client, JWT verified by Django, user row returned.
 */
export default async function MePage() {
  const t = await getTranslations("me");
  // `getTranslations("me")` scopes every lookup to the `me` namespace, so the shared
  // strings need their own translator: a scoped t("common.yes") resolves me.common.yes.
  const tCommon = await getTranslations("common");
  const { userId } = await auth();

  if (!userId) {
    return (
      <section className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground">{t("signedOut")}</p>
      </section>
    );
  }

  const api = await getServerApiClient();
  // Only `data`/`response` are used: the schema declares no error payload for this
  // endpoint, so openapi-fetch types `error` as never and narrowing on it is unsound.
  const { data, response } = await api.GET("/api/v1/me");

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground max-w-prose">{t("body")}</p>
      </div>

      {!data ? (
        <p className="border-destructive/40 bg-destructive/5 text-destructive rounded-md border px-4 py-3 text-sm">
          {t("error", { message: `HTTP ${response.status}` })}
        </p>
      ) : (
        <dl className="border-border divide-border divide-y rounded-md border text-sm">
          <Row label={t("fields.name")} value={data.full_name || tCommon("notSet")} />
          <Row label={t("fields.email")} value={data.email || tCommon("notSet")} />
          <Row label={t("fields.phone")} value={data.phone || tCommon("notSet")} />
          <Row label={t("fields.clerkId")} value={data.clerk_id} mono />
          <Row label={t("fields.id")} value={data.id} mono />
          <Row
            label={t("fields.platformAdmin")}
            value={data.is_platform_admin ? tCommon("yes") : tCommon("no")}
          />
          <Row label={t("fields.createdAt")} value={data.created_at} mono />
        </dl>
      )}
    </section>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-baseline sm:gap-4">
      <dt className="text-muted-foreground w-40 shrink-0">{label}</dt>
      <dd className={mono ? "font-mono text-xs break-all" : "break-words"}>{value}</dd>
    </div>
  );
}
