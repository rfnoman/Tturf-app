import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Button } from "@/components/ui/button";

export default async function AdminPage() {
  const t = await getTranslations("admin");

  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
      <p className="text-muted-foreground">{t("empty")}</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" asChild>
          <Link href="/admin/dashboard">{t("navDashboard")}</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/admin/support">{t("navSupport")}</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/admin/turfs">{t("navTurfs")}</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/admin/sports">{t("navSports")}</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/admin/conduct">{t("navConduct")}</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/admin/warehouse">{t("navWarehouse")}</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/admin/orders">{t("navOrders")}</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/admin/finance">{t("navFinance")}</Link>
        </Button>
      </div>
    </section>
  );
}
