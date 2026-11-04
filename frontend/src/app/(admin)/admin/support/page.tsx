import { getTranslations } from "next-intl/server";

import { PlayerLookup } from "./player-lookup";

export const metadata = { title: "Support · TurfApp" };

/**
 * Finding the right account.
 *
 * Support has to answer "I can't see my booking" from a name or an email, and the Phase
 * 06 player search cannot: it is deliberately limited to discoverable players and never
 * exposes contact details. This is the narrow exception — admins only, read-only, and
 * there is no impersonation anywhere in the app.
 */
export default async function AdminSupportPage() {
  const t = await getTranslations("support");

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </header>
      <PlayerLookup />
    </div>
  );
}
