import { auth } from "@clerk/nextjs/server";

/**
 * Player area gate.
 *
 * Protection lives here rather than in the proxy: Clerk deprecated
 * `createRouteMatcher` and recommends gating as close to the data as possible
 * (DECISIONS D12). Every page in this group is therefore signed-in only.
 */
export default async function PlayerLayout({ children }: { children: React.ReactNode }) {
  await auth.protect();
  return <>{children}</>;
}
