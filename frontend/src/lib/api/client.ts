import createClient, { type Client, type Middleware } from "openapi-fetch";

import type { paths } from "./schema";
import { API_BASE_URL } from "./config";

export type ApiClient = Client<paths>;

/** Supplies a Clerk session token, or null when nobody is signed in. */
export type TokenGetter = () => Promise<string | null | undefined>;

/**
 * Build a typed client that attaches a Clerk session token to every request.
 *
 * The token source is injected rather than imported so one implementation serves both
 * sides of the app: `useApiClient()` passes the browser's `useAuth().getToken`, and
 * `getServerApiClient()` passes the server's `(await auth()).getToken`.
 */
export function createApiClient(getToken: TokenGetter, baseUrl: string = API_BASE_URL): ApiClient {
  const client = createClient<paths>({ baseUrl });

  const auth: Middleware = {
    async onRequest({ request }) {
      const token = await getToken();
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
      return request;
    },
  };

  client.use(auth);
  return client;
}

/** A client for endpoints that need no credentials (health, public listings). */
export function createPublicApiClient(baseUrl: string = API_BASE_URL): ApiClient {
  return createClient<paths>({ baseUrl });
}
