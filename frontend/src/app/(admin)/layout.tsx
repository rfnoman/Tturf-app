import { notFound } from "next/navigation";
import { auth } from "@clerk/nextjs/server";

import { getServerApiClient } from "@/lib/api/server";

/**
 * Platform admin gate: signed in **and** `is_platform_admin` according to Django.
 *
 * The flag is deliberately read from our own API rather than a Clerk claim — roles are
 * permissions on our account record (DOMAIN §1), so Django stays the authority. The
 * backend re-checks on every endpoint; this only decides what to render.
 */
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  await auth.protect();

  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/me");

  if (!data?.is_platform_admin) {
    notFound();
  }

  return <>{children}</>;
}
