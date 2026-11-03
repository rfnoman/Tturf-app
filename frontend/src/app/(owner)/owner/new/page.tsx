import { getServerApiClient } from "@/lib/api/server";

import { RegisterTurfForm } from "./register-form";

export const metadata = { title: "Register your turf · TurfApp" };

export default async function RegisterTurfPage() {
  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/amenities");

  return <RegisterTurfForm amenities={data ?? []} />;
}
