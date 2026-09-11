"""four-letter outlet codes

Revision ID: a41d7c92e650
Revises: f7c3a91d42e8
Create Date: 2026-09-10
"""

import re

from alembic import op
import sqlalchemy as sa


revision = 'a41d7c92e650'
down_revision = 'f7c3a91d42e8'
branch_labels = None
depends_on = None

_LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
_CODE_WIDTH = 4


def _letter_code(value: int) -> str:
    encoded: list[str] = []
    for _ in range(_CODE_WIDTH):
        value, remainder = divmod(value, len(_LETTERS))
        encoded.append(_LETTERS[remainder])
    return ''.join(reversed(encoded))


def _migration_role_owns_outlets(connection: sa.Connection) -> bool:
    table_owner = connection.execute(sa.text(
        "SELECT tableowner FROM pg_tables WHERE schemaname = 'public' AND tablename = 'outlets'"
    )).scalar_one()
    current_user = connection.execute(sa.text('SELECT current_user')).scalar_one()
    return table_owner == current_user


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        'SELECT id, code FROM outlets ORDER BY created_at NULLS LAST, id'
    )).mappings().all()

    used: set[str] = set()
    replacements: list[str] = []
    for row in rows:
        code = str(row['code'] or '').strip().upper()
        if re.fullmatch(r'[A-Z]{4}', code) and code not in used:
            used.add(code)
            if code != row['code']:
                connection.execute(
                    sa.text('UPDATE outlets SET code = :code WHERE id = :id'),
                    {'code': code, 'id': row['id']},
                )
        else:
            replacements.append(row['id'])

    candidates = (_letter_code(sequence) for sequence in range(len(_LETTERS) ** _CODE_WIDTH))
    for outlet_id in replacements:
        candidate = next((value for value in candidates if value not in used), None)
        if candidate is None:
            raise RuntimeError('No four-letter outlet codes are available.')
        used.add(candidate)
        connection.execute(
            sa.text('UPDATE outlets SET code = :code WHERE id = :id'),
            {'code': candidate, 'id': outlet_id},
        )

    # Imported databases can be owned by a different PostgreSQL role. Data is
    # always normalized; the physical constraint is updated when DDL is allowed.
    if _migration_role_owns_outlets(connection):
        check_names = {
            item['name']
            for item in sa.inspect(connection).get_check_constraints('outlets')
            if item.get('name')
        }
        if 'ck_outlets_code_format' in check_names:
            op.drop_constraint('ck_outlets_code_format', 'outlets', type_='check')
        op.create_check_constraint(
            'ck_outlets_code_format',
            'outlets',
            "char_length(code) = 4 AND code ~ '^[A-Z]{4}$'",
        )


def downgrade() -> None:
    connection = op.get_bind()
    if _migration_role_owns_outlets(connection):
        op.drop_constraint('ck_outlets_code_format', 'outlets', type_='check')
        op.create_check_constraint(
            'ck_outlets_code_format',
            'outlets',
            "char_length(code) = 4 AND code = upper(code) AND code ~ '^[A-Z0-9]{4}$'",
        )
