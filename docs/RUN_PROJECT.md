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

Open `http://localhost:4200`.

### Angular + Electron desktop UI

Keep the backend running, then use:

```powershell
cd D:\Project\BrewBill
npm.cmd run desktop:dev
```

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
