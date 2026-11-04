# Deployment

DigitalOcean (Bangalore) for everything that holds data, Vercel for the frontend
(DECISIONS D71). Bangalore because it is the nearest region to Dhaka at roughly 40–60ms:
a booking page waiting on a round trip to Frankfurt is a booking page nobody uses on a
3G connection.

```
Vercel (edge)                    DigitalOcean App Platform, region blr
┌──────────────┐  HTTPS   ┌──────────────────────────────────────────┐
│  Next.js     │ ───────▶ │  api     ×2   gunicorn + uvicorn workers │
│  turfapp.…   │          │  worker  ×1   Celery                     │
└──────────────┘          │  beat    ×1   Celery beat  ← exactly one │
                          └───────────────┬──────────────────────────┘
                                          │
                     Managed Postgres 17 + PostGIS   (daily backups)
                     Managed Redis            broker · cache · SSE
                     Spaces + CDN             turf and player photos
```

Everything below has to be done once, by hand, and then never again. It is written out
rather than scripted because each step needs a decision or a credential that cannot live
in the repository.

## What you need before starting

| Thing | Where from | Used for |
|---|---|---|
| DigitalOcean account | cloud.digitalocean.com | Everything backend |
| Vercel account | vercel.com | The frontend |
| Clerk **production** instance | Clerk dashboard | Sign-in. A development instance will not serve a real domain. |
| SSLCommerz merchant account | sslcommerz.com | Live payments. Sandbox credentials are free and come first. |
| A domain | Any registrar | `turfapp.com.bd` or similar |
| Sentry project (optional) | sentry.io | Error reports. Everything works without it. |

## 1. The database cluster

Create a managed **PostgreSQL 17** cluster in `blr1`, then connect to it once and enable
the two extensions. Neither is on by default, and the second is not optional:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

`btree_gist` is what makes the bookings exclusion constraint possible — `uuid` has no
default GiST operator class, so without it the migration that prevents double-booking
fails (DECISIONS D29). If you skip this step the first deploy dies at `migrate`, which
is the right place to find out.

Create a managed **Redis** cluster in the same region. It is the Celery broker, the
cache and the Phase 09 notification channel, so it is not optional either.

## 2. Spaces, for photos

Create a Space in `blr1` and enable its CDN. Generate a Spaces access key pair.

Uploaded photos must not live on a container filesystem: App Platform replaces
containers on every deploy, and anything written to one is gone. The code switches to
S3-compatible storage the moment `AWS_STORAGE_BUCKET_NAME` is set and needs no other
change (DECISIONS D71) — the same settings would drive Cloudflare R2 or AWS S3 if this
ever moves.

## 3. The app

```bash
doctl apps create --spec .do/app.yaml
```

Then fill in the secrets. They are referenced in the spec as `${NAME}` and are **not**
in the repository:

- `DJANGO_SECRET_KEY` — generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SIGNING_SECRET`, `CLERK_FRONTEND_API_URL`
- `SSLCOMMERZ_STORE_ID`, `SSLCOMMERZ_STORE_PASSWORD`
- `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` — generate: `uv run python manage.py generate_vapid_keys`
- `SPACES_KEY`, `SPACES_SECRET`, `SPACES_BUCKET`
- `SENTRY_DSN` (optional)
- `SITE_URL` — the Vercel domain, e.g. `https://turfapp.com.bd`

## 4. Vercel

Import the repository, set the root directory to `frontend`, and add:

```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY   pk_live_…
CLERK_SECRET_KEY                    sk_live_…
NEXT_PUBLIC_API_BASE_URL            https://api.turfapp.com.bd
NEXT_PUBLIC_SITE_URL                https://turfapp.com.bd
NEXT_PUBLIC_SENTRY_DSN              (optional)
```

The `NEXT_PUBLIC_*` values are compiled into the client bundle, so **changing one needs a
redeploy, not a restart**. Setting one to an empty string is the same as not setting it
(`src/lib/env.ts`) — which is a lesson from building the production image, where Docker
turns an unset `ARG` into an empty `ENV` and `new URL("")` killed the build.

## 5. The things that are easy to forget

- **`CLERK_AUTHORIZED_PARTIES` must contain the exact frontend origin.** Django rejects
  a token whose `azp` is not listed, and the symptom is every authenticated request
  returning 401 on a deploy that otherwise looks perfect. This is the single most likely
  reason a working staging environment stops authenticating in production.
- **Point the Clerk webhook** at `https://api.…/api/v1/webhooks/clerk` and copy its
  signing secret. Without it, accounts never reach Django and every sign-in creates a
  player with no profile.
- **Point the SSLCommerz IPN** at `https://api.…/api/v1/payments/ipn/sslcommerz`.
- **Register the server's egress IP with SSLCommerz.** They refuse refund API calls from
  an unregistered address, so refunds fail in production while payments work — a failure
  that only appears the first time somebody cancels.
- **`SSLCOMMERZ_SANDBOX=false`** for live. It is `true` by default on purpose.

## 6. Backups

The managed cluster takes daily backups. That is not the same as having a backup, so:

```bash
doctl apps run <app-id> --command "python manage.py backup_database"
```

It dumps **and restores the dump into a scratch database and counts the tables**,
failing if what comes back is unusable (DECISIONS D68). Run it on a schedule, and keep
the dumps somewhere that is not the application server. The failure mode of a nightly
dump is finding out on the day it matters that it has been zero bytes for three months,
and the only thing that catches that is restoring it.

`pg_dump` must be the same major version as the server or newer. The image ships the
Postgres 17 client for exactly this reason.

## 7. Deploying after that

**The deploy workflow is disarmed.** It is `workflow_dispatch` only, so merging to main
deploys nothing — there is no app yet, and a workflow firing at infrastructure that does
not exist is noise. Once the steps above are done, add the `push: branches: [main]`
trigger back (the file says where).

Then: merge to `main`. `.github/workflows/deploy.yml` waits for the checks on that commit,
tells App Platform to deploy, and fails if the API does not come back healthy. App
Platform runs migrations as a `PRE_DEPLOY` job, so a migration failure stops the rollout
instead of leaving new code against an old schema. Vercel deploys the frontend from its
own git integration.

Set these in the repository:

| Kind | Name | Value |
|---|---|---|
| Secret | `DIGITALOCEAN_ACCESS_TOKEN` | A DO API token with write access |
| Secret | `DO_APP_ID` | From `doctl apps list` |
| Secret | `SENTRY_AUTH_TOKEN` | Optional |
| Variable | `API_BASE_URL` | `https://api.turfapp.com.bd` |
| Variable | `SENTRY_ORG`, `SENTRY_PROJECT` | Optional |

## 8. The first administrator

Platform admin is a flag on an account, not a separate kind of user:

```bash
doctl apps run <app-id> --command \
  "python manage.py shell -c \"from apps.accounts.models import User; u=User.objects.get(email='you@example.com'); u.is_platform_admin=True; u.is_staff=True; u.is_superuser=True; u.save()\""
```

Sign in through the app first so the account exists. Then register a TOTP device in the
Django admin under **TOTP devices** — `/admin/` refuses a password-only login in
production (DECISIONS D64), and the first login after that will not work without one.

## Staging

The same spec with `name: turfapp-staging`, a development-tier database, and
`SSLCOMMERZ_SANDBOX=true`. Point it at a Clerk **development** instance so test accounts
stay out of the production user list. Step 9's launch journeys run against this.
