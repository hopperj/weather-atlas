# Public HTTPS with Let's Encrypt

## Deployment for weatheratlas.ioresearch.ca

Requested 2026-09-08. The existing Caddy gateway is the certificate manager and
TLS endpoint; no Certbot container, separate renewal cron job, or manually copied
private key is required. The Caddyfile explicitly selects Let's Encrypt's
production ACME directory. Caddy obtains and renews the certificate while running.

**Current policy: HTTPS-only application traffic.** Use
`https://weatheratlas.ioresearch.ca` for the web app and native app server setting.
The HTTP listener serves only a permanent redirect to this canonical hostname
(and Caddy-managed ACME validation if needed). It does not serve app HTML, API
responses, tiles or files. This supersedes the initial temporary LAN HTTP
compatibility described in the historical issuance notes below.

HTTPS-only enforcement was activated on 2026-09-08 by removing the extra HTTP
site from `.env`, moving all application handlers into an explicit `https://`
site, and adding a redirect-only HTTP block. Only the gateway was recreated.
Compose now requires a site hostname; startup output and the example deployment
advertise HTTPS rather than an HTTP app URL.

Verification passed: 13 operations-script tests; 28 live HTTP checks covering
local/LAN/public/untrusted Host values, five paths, query preservation and a
non-mutating test POST; trusted HTTPS 200 for forecast, products and readiness;
and the public HTTP-to-HTTPS redirect. The app gateway's HTTP responses contained
no app data. The existing Let's Encrypt fingerprint/expiry remained unchanged,
all services were running, and services with health checks reported healthy.
The public HTTP redirect still came from the upstream gateway (301); the app's
own redirect is 308. No router settings were changed by this enforcement.

Initial checks at approximately 13:24 UTC:

- Public DNS (also queried through 1.1.1.1) resolves the name to `66.199.181.187`.
- No AAAA or CAA records were returned for the hostname; no CAA record was
  returned for `ioresearch.ca` either.
- The app server's primary LAN address, also returned for `wolf359.iolan`, is
  `10.0.0.146`. Its readiness endpoint reports PostgreSQL, Redis and storage ready.
- From this machine, requests to the public hostname reach a UniFi OS page,
  not Weather Atlas. HTTPS presents a self-signed `unifi.local` certificate.
  This LAN-side check alone does not establish what an off-network client sees;
  check WAN forwarding and NAT loopback/split DNS as appropriate.
- No gateway, firewall or DNS records were changed by the app-side setup.
  Issuance was initially deferred pending routing verification; the completed
  issuance is recorded below.

Preparation checks passed: Caddy validated both the existing HTTP-only address
and `weatheratlas.ioresearch.ca, :80` (initially supplied only to validation).
Compose validation and all 12 operations-script tests passed. The local forecast
still returned HTTP 200 and readiness remained healthy. During that preparation
the live address remained `:80` and no certificate order was started.

### Activated and verified, 2026-09-08 at approximately 13:43 UTC

After the user reported a TLS handshake termination from an external shell,
public port 443 no longer served the UniFi certificate. It reset connections in
the same way as the app host's mapped HTTPS port: Caddy was still HTTP-only.
The live `.env` was updated to `CADDY_SITE_ADDRESS=weatheratlas.ioresearch.ca, :80`,
validated, and only the `reverse-proxy` container was recreated. All other app,
database, collection and monitoring services were left running.

Caddy registered an ACME account and obtained a production Let's Encrypt
certificate. HTTP-01 failed (HTTP still reached the gateway redirect), then
TLS-ALPN-01 over public port 443 succeeded. Caddy logged both successful
authorization and `certificate obtained successfully`.

- Subject: `weatheratlas.ioresearch.ca`.
- Issuer: Let's Encrypt `YE1`.
- Validity: 2026-09-08 12:44:30 UTC to 2026-12-07 12:44:29 UTC.
- SHA-256 fingerprint:
  `9C:12:2F:3E:E9:8F:32:20:82:09:DA:F1:0B:B1:2B:99:2F:B1:74:B8:D2:0B:F2:1F:B2:77:33:52:EA:8C:B9:9C`.
- Standard HTTPS verification, without `-k`, passed for the public hostname;
  `/health/ready` returned HTTP 200 with all checks true, `/forecast` returned
  the app HTML, and `/api/v1/products` returned eight products.
- The app's HTTP listener redirects requests bearing the public hostname to
  HTTPS with HTTP 308. Localhost HTTP forecast and readiness remain available.
- `.env` retains owner-only `0600` permissions. Private keys were not printed,
  copied into source, or exported to the iOS app.

These HTTPS client checks ran from the app server's network using the public
hostname. The successful ACME authorization also proves that Let's Encrypt's
external validation reached the TLS listener. The user should repeat their
external `curl` command to confirm their own client path.

Public port 80 still returned an Nginx/gateway HTTP 301 at certificate verification time;
the intended forward to `10.0.0.146:18080` remains recommended. Keep public TCP
443 forwarded for certificate renewal via TLS-ALPN-01; do not place a TLS
terminator in front of Caddy without revisiting certificate management.

## Network prerequisites

Reserve the app server's LAN address so forwarding rules remain valid. For this
deployment, configure these TCP forwards on the Internet-facing gateway:

| Public port | Destination |
| --- | --- |
| 80 | `10.0.0.146:18080` |
| 443 | `10.0.0.146:8443` |

Forward to the app server, not the router's own management service. If these
ports already serve other websites, do not replace their routes: use the
existing front-end proxy to route this hostname and its ACME challenges, or
arrange DNS validation instead. The actual public TLS terminator must serve the
trusted certificate; an origin certificate behind a self-signed public proxy
does not fix browser/iOS trust.

Only forward the web gateway ports. Keep Airflow, PostgreSQL, Grafana,
Prometheus and router management private. Review application write endpoints and
authentication separately before a public launch; TLS encrypts traffic but does
not add access control.

HTTP-01 validation requires public port 80; TLS-ALPN-01 uses public port 443.
Nonstandard host ports work when the gateway translates those public ports to
the mappings above. If using IPv6 later, its DNS and firewall route must reach
this same app. DNS-01 is an alternative if inbound verification is unavailable,
but needs a separate DNS automation setup; it is not configured here.

## Activate after routing is ready

Keep the existing port assignments in `.env` and change only the site address:

```dotenv
APP_BIND_ADDRESS=0.0.0.0
APP_PORT=18080
HTTPS_PORT=8443
CADDY_SITE_ADDRESS=weatheratlas.ioresearch.ca
```

The site address must be a single hostname: do not append `, :80` or specify
`http://`. The Caddyfile explicitly serves all application routes on HTTPS only.
A separate HTTP block redirects every hostname/path to the canonical HTTPS URL,
preserving path and query. Its target does not use the untrusted incoming Host
header. This includes requests to localhost, the LAN IP and `wolf359.iolan`.

Port 80 may remain reachable for redirection and certificate validation; it is
not an alternate HTTP app. All app and API clients should start directly with
the HTTPS URL so their first request is encrypted too. The certificate covers
the public hostname, not local IP addresses. LAN clients must have working NAT
loopback or an equivalent route to the domain's HTTPS port.

Validate and then recreate **only** the gateway to apply the changed environment:

```bash
docker compose run --rm --no-deps reverse-proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose up -d --no-deps reverse-proxy
```

The Caddy admin endpoint is disabled, so `caddy reload` is not available. Do not
restart the ETL stack or run database migrations for this change. Avoid repeated
issuance attempts against production while routing is broken.

## Verify actual issuance

```bash
curl -fsS https://weatheratlas.ioresearch.ca/health/ready
curl -I http://weatheratlas.ioresearch.ca/forecast
curl -I https://weatheratlas.ioresearch.ca/forecast
curl -I http://localhost:18080/health/ready
docker compose logs --since=10m reverse-proxy
```

HTTPS must succeed with normal certificate verification, without `-k`, on both
the LAN and an independent external network (for example, cellular). Check the
certificate subject alternative name, trusted issuer and expiry, the HTTP to
HTTPS redirect, forecast page and API requests. A 200 response containing router
HTML is not an app health check. Do not disable iOS or browser certificate
validation to work around a routing or issuance problem.

The localhost HTTP check must return HTTP 308 and a Location under
`https://weatheratlas.ioresearch.ca`, not a JSON readiness response. Check this
for `/`, `/forecast`, `/api/v1/products`, `/tiles/` and `/health/ready` as well.
Internal Docker links and private administrative ports are outside this public
gateway policy and remain unchanged.

Use `https://weatheratlas.ioresearch.ca` as the native app's server address only
after this verification. Changing the web certificate does not update previously
installed iOS app settings.

## Renewal, storage and rollback

Certificate keys and ACME account state persist under
`${WEATHERAPP_DATA_DIR}/caddy/data`; configuration state persists under
`${WEATHERAPP_DATA_DIR}/caddy/config`. These existing bind mounts survive container
recreation. Protect the data directory as secret material, never commit its
contents, and do not delete it as part of image cleanup. Keep Docker/Caddy running
and validation routing available for renewal. No precise certificate lifetime is
assumed; inspect the certificate and let Caddy schedule renewal.

For rollback, retain the HTTPS-only policy and restore the last known working
HTTPS configuration while preserving the certificate data directory. Do not
restore the old `:80` application site or disable certificate validation. Router
changes are managed separately; browser HSTS policy continues to require HTTPS.

## References

- [Caddy automatic HTTPS, redirects and certificate storage](https://caddyserver.com/docs/automatic-https)
- [Caddy ACME issuer configuration](https://caddyserver.com/docs/caddyfile/options#acme-ca)
- [Let's Encrypt challenge types and network requirements](https://letsencrypt.org/docs/challenge-types/)
