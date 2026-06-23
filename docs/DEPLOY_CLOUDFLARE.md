# Cloudflare DNS + Access runbook

End-to-end setup for routing custom subdomains to your Railway services and gating them with Cloudflare Access. Assumes you already own a domain managed by Cloudflare DNS (use the apex-domain dashboard at https://dash.cloudflare.com).

> If you're following the dev + prod environment split from the main README, you'll do everything below **twice** — once for dev (`scholar-dev` / `api.scholar-dev`) and once for prod (`scholar` / `api.scholar`). Same steps, different Railway target hostnames per env.

> Replace `scholar.yourdomain.com` with your actual subdomain everywhere below.

## 1. Get the Railway public hostnames

After provisioning the two services in Railway (see the main README "Deploy to Railway + Cloudflare" section), Railway gives each one a public hostname under `*.up.railway.app`:

- Backend  : `daily-scholar-backend-production.up.railway.app`
- Frontend : `daily-scholar-frontend-production.up.railway.app`

You'll find these in the Railway dashboard → Service → Settings → Public Networking.

## 2. Cloudflare DNS records

In the Cloudflare dashboard for your domain → DNS → Records:

| Type  | Name | Target | Proxy | TTL |
|---|---|---|---|---|
| CNAME | `scholar` (frontend) | `daily-scholar-frontend-production.up.railway.app` | **Proxied** (orange cloud) | Auto |
| CNAME | `api.scholar` (backend) | `daily-scholar-backend-production.up.railway.app` | **Proxied** (orange cloud) | Auto |

Proxy mode "on" puts Cloudflare in front of the traffic so:

- Cloudflare issues + auto-rotates the TLS cert (no Let's Encrypt config)
- WAF + bot mitigation + analytics are free
- Access can intercept requests on these hostnames

## 3. Cloudflare SSL/TLS mode

Cloudflare → SSL/TLS → Overview → set encryption mode to **Full (strict)**.

Railway terminates TLS on its own end (`*.up.railway.app` cert is valid), so Full (strict) means CF↔Railway is encrypted with verified certs. Don't use Flexible (it leaves the CF→origin hop unencrypted).

## 4. Cloudflare Access (Zero Trust)

This is the auth layer. The free tier supports up to 50 users with email-based identity (one-time-PIN sent to email, or Google/GitHub SSO). The backend's `get_current_user_id()` dependency already reads the `Cf-Access-Authenticated-User-Email` header that Access injects — no app code change needed.

### One-time Zero Trust setup

If you've never used CF Zero Trust on this account:

1. https://one.dash.cloudflare.com → pick a team name (the subdomain for the Access auth pages, e.g. `daily-scholar`)
2. Choose the **Free** plan when prompted (up to 50 users)
3. Settings → Authentication → add an identity provider. The simplest path is **One-time PIN** (email OTP, no SSO config). Add Google or GitHub if you prefer SSO.

### Add the application

Zero Trust dashboard → Access → Applications → Add an application → **Self-hosted**:

| Field | Value |
|---|---|
| Application name | Daily Scholar |
| Session duration | 24 hours (default) |
| Application domain | `scholar.yourdomain.com` (the frontend hostname) |
| Identity providers | One-time PIN (and any SSO you added) |

Add a second app entry for the backend hostname (`api.scholar.yourdomain.com`) using the same settings — both need to be Access-protected so the JWT propagates to API calls.

### Access policy

For each app, add a policy:

- **Policy name:** "Daily Scholar users"
- **Action:** Allow
- **Include rule:** Emails → list the emails of everyone you want in (yours + the ~30 beta testers later)

Save. Access is now enforcing.

### Verify the email header reaches the backend

After deploying, hit any backend endpoint while logged in to Access and inspect the request headers (browser devtools → Network → any request to `api.scholar.yourdomain.com`). You should see:

```
Cf-Access-Authenticated-User-Email: you@example.com
Cf-Access-Jwt-Assertion: eyJ...
```

The first one is what the backend reads via `get_current_user_id()`.

## 5. Adding beta testers

Zero Trust dashboard → Access → Applications → Daily Scholar (the **prod** app) → Policies → Edit "Daily Scholar users" → add their emails to the Include list. They'll get an email OTP on first visit. Removing them is just deleting from the list.

If you're running dev + prod environments, keep the dev Access app locked to your email only — beta testers should only ever see the stable prod env.

This is the "auth flip" the schema migration in Phase 0 was preparing for — adding users is a CF policy edit, not a code change.

## 6. CORS gotcha

The backend's CORS middleware allows `FRONTEND_URL`. Update the Railway env on the backend service:

```
FRONTEND_URL=https://scholar.yourdomain.com
```

Without that the browser will block the cross-origin requests with CORS errors.

## 7. Optional: zero-egress Backblaze pairing

If `STORAGE_BACKEND=b2`, you can save B2 egress fees by routing PDF downloads through Cloudflare. In Cloudflare:

1. Add a CNAME: `pdfs.scholar.yourdomain.com` → `s3.us-east-005.backblazeb2.com`, proxied
2. In B2: add `pdfs.scholar.yourdomain.com` as an allowed hostname on the bucket (Bucket settings → CORS → add origin)
3. Set `B2_ENDPOINT_URL=https://pdfs.scholar.yourdomain.com` on the backend

Presigned URLs will then point at the CF-routed hostname, and Backblaze charges $0 egress on traffic that exits via Cloudflare (per their bandwidth alliance agreement).

This is optional — at single-user scale, raw B2 egress will cost cents per month anyway.

## 8. Health-check after deploy

```bash
# DNS resolves through CF
dig scholar.yourdomain.com +short
dig api.scholar.yourdomain.com +short

# Hit Access — should redirect to the CF Access OTP login on first visit
curl -I https://scholar.yourdomain.com

# Logged in (browser): backend /health/deep should return 200 healthy with
# db.url_scheme = postgresql+psycopg
```

If `/health/deep` shows `db` ✗ on the deployed backend, double-check the Railway Postgres add-on is attached and DATABASE_URL is populated.
