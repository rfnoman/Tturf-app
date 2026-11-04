/**
 * Disposable Clerk accounts for end-to-end tests.
 *
 * The Phase 01 happy path is *onboarding*, which by definition needs an account that
 * has never onboarded — so each run creates a fresh Clerk user through the Backend API
 * and deletes it afterwards. Reusing one fixed account would pass once and then fail
 * for every run after it.
 *
 * Addresses use Clerk's `+clerk_test` convention: on a development instance those skip
 * real email delivery and accept the fixed verification code, which is what makes an
 * unattended sign-in possible at all.
 */

const CLERK_API = "https://api.clerk.com/v1";

export type TestUser = {
  id: string;
  identifier: string;
  password: string;
  firstName: string;
  lastName: string;
};

export function clerkSecretKey(): string | undefined {
  return process.env.CLERK_SECRET_KEY;
}

/**
 * Retry anything Clerk rejected for rate limiting.
 *
 * A full run signs in around fifty throwaway accounts within a couple of minutes, which
 * is enough to exhaust a development instance's limit — more so when runs follow each
 * other. A 429 says "later", not "no", so treating it as a failure reports a broken app
 * when nothing is broken.
 */
export async function retryWhileRateLimited<T>(
  what: string,
  attempt: () => Promise<T>,
): Promise<T> {
  // Long waits on purpose: Clerk's limit is a sustained one, so a run that follows
  // another closely needs the window to roll over rather than a quick second try.
  const backoff = [3_000, 6_000, 12_000, 24_000, 45_000];
  let last: unknown;

  for (let tries = 0; ; tries += 1) {
    try {
      return await attempt();
    } catch (error) {
      last = error;
      if (!/429|Too Many Requests/i.test(String(error)) || tries >= backoff.length) break;
      await new Promise((resolve) => setTimeout(resolve, backoff[tries]));
    }
  }

  throw new Error(`${what} kept hitting Clerk's rate limit: ${String(last)}`);
}

async function clerkRequest(path: string, init: RequestInit = {}): Promise<Response> {
  const secret = clerkSecretKey();
  if (!secret) throw new Error("CLERK_SECRET_KEY is required to manage test users.");

  return retryWhileRateLimited(`${init.method ?? "GET"} ${path}`, async () => {
    const response = await fetch(`${CLERK_API}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${secret}`,
        "Content-Type": "application/json",
        ...init.headers,
      },
    });
    if (response.status === 429) throw new Error("429 Too Many Requests");
    return response;
  });
}

export async function createTestUser(): Promise<TestUser> {
  // Unique per run so parallel workers and repeated runs never collide.
  const suffix = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  const identifier = `e2e+clerk_test+${suffix}@turfapp.dev`;
  const password = `E2e-TurfApp-${suffix}!`;

  const response = await clerkRequest("/users", {
    method: "POST",
    body: JSON.stringify({
      email_address: [identifier],
      password,
      first_name: "E2E",
      last_name: "Player",
      skip_password_checks: true,
    }),
  });

  if (!response.ok) {
    throw new Error(
      `Could not create a Clerk test user: ${response.status} ${await response.text()}`,
    );
  }

  const { id } = (await response.json()) as { id: string };
  return { id, identifier, password, firstName: "E2E", lastName: "Player" };
}

export async function deleteTestUser(id: string): Promise<void> {
  // Cleanup must never fail a run: a leaked development user is noise, a failed
  // teardown masking a real result is not.
  try {
    await clerkRequest(`/users/${id}`, { method: "DELETE" });
  } catch {
    // ignored on purpose
  }
}

/** Origin of the Django API, as the browser must address it from inside `evaluate`. */
export function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
}
