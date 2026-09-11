from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def next_prefixed_number(
    session: Session,
    column: Any,
    prefix: str,
    *,
    width: int = 6,
) -> str:
    """Return the next globally unique number for a prefixed identifier.

    Number columns such as invoice_number are globally unique in the database,
    so counting rows inside one tenant can reuse a value owned by another tenant
    or by restored data. PostgreSQL's transaction-level advisory lock also
    serializes numbering when multiple POS devices submit at the same time.
    """
    bind = session.get_bind()
    if bind.dialect.name == 'postgresql':
        lock_name = f'brewbill-number:{column.table.name}:{prefix}'
        session.execute(select(func.pg_advisory_xact_lock(func.hashtext(lock_name))))

    existing_values = session.scalars(
        select(column).where(column.startswith(prefix, autoescape=True))
    ).all()
    highest = 0
    for value in existing_values:
        suffix = str(value)[len(prefix):]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f'{prefix}{highest + 1:0{width}d}'
