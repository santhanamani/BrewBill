# Tenant branding

In Administration, select the tenant, open **Branding**, choose a logo and cover,
then click **Save Changes**. Uploading previews an image; saving publishes it only
for the selected tenant. Switching tenant during an upload never applies the old
upload to the new selection.

| Image | Recommended dimensions | Aspect ratio | Limit | Display |
| --- | --- | --- | --- | --- |
| Logo | 512 x 512 px | 1:1 | 2 MB | Circular; keep artwork within the centre 80% |
| Cover | 1600 x 1000 px | 8:5 | 5 MB | 12 px preview corners; hero crops responsively |

Use still PNG, JPEG or WebP files. Do not bake rounded corners into the file.
Minimum dimensions are 64 x 64 px; maximum is 8000 px per side and 20 megapixels.
The server validates actual image content, removes metadata by re-encoding pixels,
and stores unique WebP files. Logo output is at most 1024 x 1024; cover output is
at most 2400 x 1600, maintaining aspect ratio.

Files live in `backend/storage/tenant-branding/<tenant UUID>/` on the project's
drive (D: in this installation). Back up this directory together with PostgreSQL.
Media is public so login can display it before authentication; do not upload
private documents. Only Super Administrators can upload and publish branding.
Previous and unsaved uploads are retained, not deleted automatically.

Login checks the trimmed, case-insensitive code automatically. A verified active
tenant supplies the name, logo and cover. Changing the code immediately removes
the previous tenant preview and clears the password/MFA challenge. Unknown or
inactive codes disable login; connection failures offer a retry. No other tenant
is silently selected. Missing/broken images use the application's default images.

No schema migration is required. Fresh backend environments must install the
dependencies from `backend/pyproject.toml`, including Pillow.

Regression checks:

```powershell
& backend/.venv/Scripts/python.exe -m pytest backend/tests -q
node --test scripts/test-tenant-branding.cjs
npm.cmd run build
```

The component-state tests exercise races with mocked services; backend tests use
isolated SQLite and temporary media directories, never production tenant records.
