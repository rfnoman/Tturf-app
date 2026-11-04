import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { StoreBrowser } from "./store-browser";

export const metadata = { title: "Store · TurfApp" };

/**
 * The store, arranged around the player's next match (DOMAIN §9).
 *
 * The match comes first because that is why somebody opens this page the evening before
 * a game: they want water and a banana at the turf, not a shopping trip.
 */
export default async function StorePage() {
  const api = await getServerApiClient();
  const [home, categories, cart, addresses, matches] = await Promise.all([
    api.GET("/api/v1/store/home"),
    api.GET("/api/v1/product-categories"),
    api.GET("/api/v1/store/cart"),
    api.GET("/api/v1/me/addresses"),
    api.GET("/api/v1/matches/mine"),
  ]);

  const t = await getTranslations("store");

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </header>

      <StoreBrowser
        home={home.data}
        categories={categories.data ?? []}
        initialCart={cart.data}
        addresses={addresses.data ?? []}
        matches={matches.data ?? []}
      />
    </div>
  );
}
