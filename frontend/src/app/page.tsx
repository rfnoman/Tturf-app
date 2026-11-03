import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Button } from "@/components/ui/button";

export default async function HomePage() {
  const t = await getTranslations("home");

  return (
    <section className="flex flex-col gap-6 py-10">
      <div className="flex flex-col gap-3">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t("heading")}</h1>
        <p className="text-muted-foreground max-w-prose text-base">{t("body")}</p>
      </div>
      <div className="flex flex-wrap gap-3">
        <Button asChild>
          <Link href="/play">{t("ctaPlay")}</Link>
        </Button>
        <Button variant="outline" asChild>
          <Link href="/turfs">{t("ctaOwner")}</Link>
        </Button>
      </div>
    </section>
  );
}
