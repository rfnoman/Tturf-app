import { getServerApiClient } from "@/lib/api/server";

import { CreateSquadForm } from "./create-form";

export const metadata = { title: "New squad · TurfApp" };

export default async function NewSquadPage() {
  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/sports");

  return <CreateSquadForm sports={data ?? []} />;
}
