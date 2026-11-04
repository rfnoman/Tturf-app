import { auth } from "@clerk/nextjs/server";
import { getLocale } from "next-intl/server";

import { type ApiClient, createApiClient } from "./client";

/**
 * Typed API client for Server Components, Server Actions and Route Handlers.
 *
 * Built per call: `auth()` is request-scoped, so a module-level client would pin one
 * request's token for every later caller.
 */
export async function getServerApiClient(): Promise<ApiClient> {
  const { getToken } = await auth();
  return createApiClient(getToken, undefined, await getLocale());
}
