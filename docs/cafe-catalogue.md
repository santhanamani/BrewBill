# Cafe catalogue and images

54 global definitions: 38 existing products repaired and 16 new cafe items.
Each product has its own transparent PNG in `public/assets/images/products/cafe/`.
Built-in image generation was used; exact prompts are recorded in
`cafe-image-prompts.json` plus the subjects in `backend/seed_data/catalogues/cafe.json`.

## Install on another backend

From `backend`, using its virtual environment:

```powershell
python -m app.cafe_catalogue
python -m app.cafe_catalogue --apply
```

The first command previews without committing. Apply validates transparency,
missing files and byte-identical duplicate images, copies into the configured
media data root, writes a change manifest under `.codex-runtime/catalogue-backups`,
then commits. Existing files with different contents are never overwritten.
Only known bundled/default product paths are repaired; custom uploads are preserved.
Repeating apply is idempotent. Do not run the demo seed to install this catalogue.

Local installation: `D:/BrewBill-Data_folder/products/cafe/`.
Database values are relative, e.g. `products/cafe/apple-juice.png`.
Both Global Products and POS resolve these through the backend `/api/media/` route.
The POS no longer substitutes unrelated sprite/atlas pictures.

## Superadmin image uploads

In Global Products, Add/Edit now has a file picker and preview instead of an
image URL textbox. Choose PNG, JPEG or WebP (up to 5 MB, minimum 64 x 64 pixels),
then click **Save Changes** to publish. Transparent backgrounds are preserved;
the uploader does not remove backgrounds from opaque photos.

Uploads are stored under `BREWBILL_DATA_PATH/products/global-uploads/` with unique
WebP filenames. The database stores only the relative path. Images are served by
Python at `/api/media/products/global-uploads/...`, not by frontend assets.
The existing `public/assets/images/products/cafe/` files are installation sources;
runtime catalogue images come from `BREWBILL_DATA_PATH/products/cafe/`.

Saving a master image updates its mapped legacy product image paths in the same
transaction. All outlets use the master image when loading their catalogue/POS;
no remapping is necessary. Already-open screens need a catalogue refresh/reopen
to fetch the new path. Outlet prices, stock, favourites and taxes are unchanged.
Uploading alone (or cancelling the edit) does not publish an image. Old/uploaded
files are retained; cancelling does not delete existing product photos.

Restart the Python backend after changing `BREWBILL_DATA_PATH` in `backend/.env`.
The backend process must have read/write permission to that directory. Keep the
existing relative folders when moving the data root; no frontend rebuild is
needed merely to change this backend directory.

New products are Global Master definitions only. Map the desired products to an
outlet and configure selling price, GST, stock and availability before billing.
Existing outlet mappings, prices, taxes, stock and favourites are untouched.
The catalogue covers common cafe items, not every possible menu item.

For a deliberately incomplete asset set, `--allow-pending-images` preserves old
images and leaves new image paths null (standard placeholder) until a later run.
This flag was not needed for the completed 54-image local installation.
