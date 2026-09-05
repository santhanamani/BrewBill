# BrewBill – Windows Run Guide

## Daily development run

Open two PowerShell terminals.

### 1. FastAPI backend

```powershell
cd D:\Project\BrewBill\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API: `http://127.0.0.1:8000/api`
- Swagger: `http://127.0.0.1:8000/docs`

### 2. Angular browser UI

```powershell
cd D:\Project\BrewBill
npm.cmd run start
```

Open `http://127.0.0.1:4200`.

### Angular + Electron desktop UI

Keep the backend running, then use the following **instead of** the browser UI command above. It starts its own Angular server; do not run both UI commands together.

```powershell
cd D:\Project\BrewBill
npm.cmd run desktop:dev
```

### Blank page / NG0203 followed by StandaloneService NG0200

Stop the existing Angular/desktop development commands with Ctrl+C, close the old Electron window, and run only one UI command again. Sign in again after restarting. Unsaved bills are not retained by a full reload.

The development server and Electron now both use `127.0.0.1:4200`. HMR and dependency prebundling are disabled to avoid retaining or mixing Angular injector/module state while investigating this runtime failure. Source edits use full-page live reload instead; save or hold a bill before editing source files. No database reset or reseed is needed. If it recurs after a clean restart, capture the complete first NG0203 stack trace (not only the subsequent NG0200 messages).

## Demo login

Cafe / tenant code: `BHV-RSP`

| Access | Username | Password |
|---|---|---|
| Tenant admin | `admin` | `Admin@123` |
| Cashier | `cashier` | `Cashier@123` |
| Platform super admin | `superadmin` | `SuperAdmin@123` |

Change all development passwords before a production deployment.

The Super Admin account never receives application tokens after the password step alone. On first login, register the displayed setup key in an authenticator app and enter the current six-digit code. Every later Super Admin login requires the password and a fresh authenticator code. Tenant admins and cashiers continue to use the tenant-code login flow.

## First-time setup

### Node dependencies

```powershell
cd D:\Project\BrewBill
npm.cmd install
```

### Python environment

```powershell
cd D:\Project\BrewBill\backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

### PostgreSQL database

```powershell
cd D:\Project\BrewBill
.\scripts\setup-postgres.ps1
```

The script securely requests the PostgreSQL administrator and BrewBill role passwords, creates the role/database, runs Alembic migrations, imports the JSON fixture, grants runtime permissions, and writes `backend\.env`.

Do not commit or share `backend\.env`.

## Apply later migrations and fixture updates

```powershell
cd D:\Project\BrewBill
.\scripts\migrate-and-seed.ps1
```

The seed importer is idempotent. Operational data remains in PostgreSQL; Python source files do not contain catalogue rows.

## Validation

```powershell
cd D:\Project\BrewBill
npm.cmd run build
npm.cmd run test:license
```

```powershell
cd D:\Project\BrewBill\backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

## Build Windows installer

```powershell
cd D:\Project\BrewBill
npm.cmd run desktop:package
```

Output: `release\BrewBill-POS-1.0.0-Setup.exe`

## Payment terminal behaviour

Configure the provider, gateway URL, and API key under **Settings → Payment Terminal**.

- Connected UPI/Card terminal: BrewBill requests a real capture and stores its reference.
- Terminal not configured or unavailable: BrewBill records an explicitly marked manual payment.
- Terminal decline: the bill is not completed.

The configured gateway must expose:

- `GET {gateway}/health`
- `POST {gateway}/payments`

## Common checks

```powershell
Get-Service -Name "postgresql*"
Get-NetTCPConnection -State Listen -LocalPort 8000,4200
```

If the UI reports an expired session, sign in again only after confirming the backend is running. Access-token renewal is automatic through the refresh-token endpoint.
