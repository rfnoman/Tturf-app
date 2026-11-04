/**
 * Reading environment variables that might be set to nothing (Phase 11 step 8).
 *
 * `process.env.X ?? fallback` does not do what it looks like it does. `??` only catches
 * `null` and `undefined`, and an environment variable set to the **empty string** is
 * neither — so a deployment that declares `NEXT_PUBLIC_SITE_URL=` with no value gets
 * `""` rather than the fallback.
 *
 * Found by building the production image: Docker turns an unset `ARG` into an empty
 * `ENV`, and `new URL("")` threw during `next build` with `ERR_INVALID_URL`. Every
 * container platform does this, so it would have failed in exactly the same way on the
 * first real deploy.
 */
export function env(value: string | undefined, fallback: string): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : fallback;
}
