"""global four-character outlet codes

Revision ID: f7c3a91d42e8
Revises: d6f82b9a10c4
Create Date: 2026-09-10
"""

import re

from alembic import op
import sqlalchemy as sa


revision = 'f7c3a91d42e8'
down_revision = 'd6f82b9a10c4'
branch_labels = None
depends_on = None

_BASE36 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def _base36(value: int) -> str:
    encoded = ''
    while value:
        value, remainder = divmod(value, len(_BASE36))
        encoded = _BASE36[remainder] + encoded
    return encoded.rjust(3, '0')


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        'SELECT id, code FROM outlets ORDER BY created_at NULLS LAST, id'
    )).mappings().all()

    used: set[str] = set()
    replacements: list[str] = []
    for row in rows:
        code = str(row['code'] or '').strip().upper()
        if re.fullmatch(r'[A-Z0-9]{4}', code) and code not in used:
            used.add(code)
            if code != row['code']:
                connection.execute(
                    sa.text('UPDATE outlets SET code = :code WHERE id = :id'),
                    {'code': code, 'id': row['id']},
                )
        else:
            replacements.append(row['id'])

    sequence = 1
    for outlet_id in replacements:
        while sequence < len(_BASE36) ** 3:
            candidate = f'O{_base36(sequence)}'
            sequence += 1
            if candidate not in used:
                used.add(candidate)
                connection.execute(
                    sa.text('UPDATE outlets SET code = :code WHERE id = :id'),
                    {'code': candidate, 'id': outlet_id},
                )
                break
        else:
            raise RuntimeError('No four-character outlet codes are available.')

    # Restored databases can retain ``postgres`` as the table owner while the
    # runtime migration role has data privileges only. Always repair the data;
    # add the physical constraints whenever the migration role owns the table.
    table_owner = connection.execute(sa.text(
        "SELECT tableowner FROM pg_tables WHERE schemaname = 'public' AND tablename = 'outlets'"
    )).scalar_one()
    current_user = connection.execute(sa.text('SELECT current_user')).scalar_one()
    if table_owner == current_user:
        op.drop_constraint('uq_outlet_tenant_code', 'outlets', type_='unique')
        op.alter_column('outlets', 'code', existing_type=sa.String(length=32), type_=sa.String(length=4), nullable=False)
        op.create_unique_constraint('uq_outlets_code', 'outlets', ['code'])
        op.create_check_constraint(
            'ck_outlets_code_format',
            'outlets',
            "char_length(code) = 4 AND code = upper(code) AND code ~ '^[A-Z0-9]{4}$'",
        )


def downgrade() -> None:
    op.drop_constraint('ck_outlets_code_format', 'outlets', type_='check')
    op.drop_constraint('uq_outlets_code', 'outlets', type_='unique')
    op.alter_column('outlets', 'code', existing_type=sa.String(length=4), type_=sa.String(length=32), nullable=False)
    op.create_unique_constraint('uq_outlet_tenant_code', 'outlets', ['tenant_id', 'code'])
