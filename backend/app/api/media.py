import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..media_storage import media_file_path, normalise_media_path


router = APIRouter(prefix='/api/media', tags=['media'])


@router.get('/{relative_path:path}', include_in_schema=False)
def read_media(relative_path: str):
    normalised = normalise_media_path(relative_path)
    path = media_file_path(normalised)
    if not path.is_file():
        raise HTTPException(404, 'Image not found.')
    media_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    return FileResponse(path, media_type=media_type, headers={
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'public, max-age=86400',
    })
