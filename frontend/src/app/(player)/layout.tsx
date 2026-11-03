import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";

import { getServerApiClient } from "@/lib/api/server";

/**
 * Player area gate.
 *
 * Protection lives here rather than in the proxy: Clerk deprecated
 * `createRouteMatcher` and recommends gating as close to the data as possible
 * (DECISIONS D12). Every page in this group is therefore signed-in only.
 *
 * It also enforces the phase 01 rule that a new player is *forced* through onboarding:
 * `/me/profile` creates the profile on first access, so this is also what gives a
 * brand-new Clerk account its `PlayerProfile` row.
 */
export default async function PlayerLayout({ children }: { children: React.ReactNode }) {
  await auth.protect();

  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/me/profile");

  // A backend that is unreachable should not trap the player in a redirect loop, so an
  // absent response falls through rather than being treated as "not onboarded".
  if (data && !data.onboarding_completed) {
    redirect("/onboarding");
  }

  return <>{children}</>;
}
