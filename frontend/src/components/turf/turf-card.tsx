import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { cn } from "cn";

import type { Turf } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";

/**
 * One turf in a listing.
 *
 * Reused by discovery, the owner dashboard and the admin review queue, so everything
 * optional is a prop: `action` for owner/admin buttons, `status` for the review badge
 * players never see.
 */
export async function TurfCard({
  turf,
  href,
  status,
  action,
  className,
}: {
  turf: Turf;
  href?: string;
  status?: { label: string; tone: "default" | "secondary" | "outline" | "destructive" };
  action?: React.ReactNode;
  className?: string;
}) {
  const t = await getTranslations("turfs");
  const photo = turf.photos?.[0];

  const body = (
    <>
      <div
        aria-hidden
        className="bg-muted relative h-32 w-full shrink-0 overflow-hidden sm:h-auto sm:w-40"
      >
        {photo?.image ? (
          // Turf photos come from the API's own storage, which Next's optimizer is not
          // configured for; a plain <img> avoids a build-time remotePatterns list that
          // would have to track every deployment's media host.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={photo.image} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="text-muted-foreground flex h-full w-full items-center justify-center text-3xl">
            {turf.sports?.[0]?.icon ?? "🏟️"}
          </div>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-base font-semibold">{turf.name}</h3>
            <p className="text-muted-foreground truncate text-xs">
              {turf.area}
              {turf.distance_km != null && ` · ${t("kmAway", { km: turf.distance_km })}`}
            </p>
          </div>
          {status && (
            <Badge variant={status.tone} className="shrink-0">
              {status.label}
            </Badge>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {turf.sports?.map((sport) => (
            <Badge key={sport.slug} variant="secondary" className="text-[0.625rem]">
              <span aria-hidden className="mr-1">
                {sport.icon}
              </span>
              {sport.name}
            </Badge>
          ))}
        </div>

        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-1">
          <p className="text-muted-foreground text-xs">
            {t("groundCount", { count: turf.ground_count })}
            {turf.price_from && ` · ${t("priceFrom", { price: turf.price_from })}`}
          </p>
          {action}
        </div>
      </div>
    </>
  );

  const shell = cn(
    "bg-card flex flex-col overflow-hidden rounded-xl border shadow-sm sm:flex-row",
    href && "hover:bg-muted/40 transition-colors",
    className,
  );

  return href ? (
    <Link href={href} className={shell}>
      {body}
    </Link>
  ) : (
    <article className={shell}>{body}</article>
  );
}
