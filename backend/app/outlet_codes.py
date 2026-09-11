from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Outlet


_LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
_OUTLET_CODE_WIDTH = 4
_MAX_OUTLET_CODES = len(_LETTERS) ** _OUTLET_CODE_WIDTH


def _letter_code(value: int) -> str:
    encoded: list[str] = []
    for _ in range(_OUTLET_CODE_WIDTH):
        value, remainder = divmod(value, len(_LETTERS))
        encoded.append(_LETTERS[remainder])
    return ''.join(reversed(encoded))


def next_outlet_code(session: Session) -> str:
    """Allocate a globally unique outlet code containing four uppercase letters."""
    if session.get_bind().dialect.name == 'postgresql':
        session.execute(select(func.pg_advisory_xact_lock(func.hashtext('brewbill-outlet-code'))))

    used = {
        str(code).strip().upper()
        for code in session.scalars(select(Outlet.code)).all()
        if code
    }
    used.update(
        item.code.strip().upper()
        for item in session.new
        if isinstance(item, Outlet) and item.code
    )
    for sequence in range(_MAX_OUTLET_CODES):
        candidate = _letter_code(sequence)
        if candidate not in used:
            return candidate
    raise ValueError('No four-letter outlet codes are available.')
