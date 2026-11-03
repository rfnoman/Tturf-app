import { auth } from "@clerk/nextjs/server";

/**
 * Turf owner area gate. Signed-in only for now; Phase 02 adds the object-level check
 * that the user actually holds an owner/manager `TurfMembership` for the turf in hand.
 */
export default async function OwnerLayout({ children }: { children: React.ReactNode }) {
  await auth.protect();
  return <>{children}</>;
}
