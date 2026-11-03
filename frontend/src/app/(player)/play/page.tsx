import { getTranslations } from "next-intl/server";

export default async function PlayPage() {
  const t = await getTranslations("player");

  return (
    <section className="flex flex-col gap-3">
      <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
      <p className="text-muted-foreground">{t("empty")}</p>
    </section>
  );
}
