import { env } from "@/lib/env";

/**
 * Origin of the Django API — no path suffix.
 *
 * The generated schema's path keys already carry the `/api/v1` prefix (for example
 * `/api/v1/me`), so appending it here would produce `/api/v1/api/v1/me`.
 */
export const API_BASE_URL = env(process.env.NEXT_PUBLIC_API_BASE_URL, "http://127.0.0.1:8000");
