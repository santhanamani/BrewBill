# Refresh-safe sessions and catalogue loading

The app stores only its token pair and API identity in sessionStorage. A normal
or hard reload in the same window restores credentials, then verifies the current
user and tenant/outlet context with the API before initial route guards run.
Passwords, cached roles and business data are not stored. Closing the session or
explicit logout requires a new login; this is not persistent Remember Me support.
Existing memory-only sessions require one new login after this update.

Expired access tokens renew through a shared refresh request. Invalid credentials
are cleared; temporary connection failures retain credentials and show a retry
option without granting access. Logout and new-login races cannot revive an old
session. MFA challenges are not persisted as authenticated sessions.

Product and outlet catalogue requests now batch inventory reads and eager-load
related masters. No stock-response cache was added: subsequent requests still
read current, tenant/outlet-scoped inventory. A local 38-product sample reduced
SELECT counts from 81 to 7 for POS products and 42 to 5 for outlet catalogue.
These are backend measurements, not a guarantee of zero end-to-end latency.

## Verification

- `node --test scripts/test-session-restore.cjs scripts/test-products-stock.cjs scripts/test-tenant-branding.cjs`
- From backend: `.venv/Scripts/python.exe -m pytest`
- `npm.cmd run build`
- Live check: sign in, open Products, press Ctrl+Shift+R, and verify the same
  route, user, tenant/outlet and fresh stock remain. Also test explicit logout.
- Unsaved form/cart restoration is not part of this change.
