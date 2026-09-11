from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, insert
from sqlalchemy.orm import Session

from app.numbering import next_prefixed_number


def test_next_prefixed_number_uses_highest_existing_suffix_not_row_count() -> None:
    engine = create_engine('sqlite+pysqlite:///:memory:')
    metadata = MetaData()
    documents = Table(
        'numbering_documents',
        metadata,
        Column('id', Integer, primary_key=True),
        Column('number', String(80), unique=True, nullable=False),
    )
    metadata.create_all(engine)

    with Session(engine) as session:
        session.execute(insert(documents), [
            {'number': 'BH-MAIN-POS01-2026-000001'},
            {'number': 'BH-MAIN-POS01-2026-000009'},
            {'number': 'BH-OTHER-POS01-2026-000100'},
        ])
        session.commit()

        generated = next_prefixed_number(
            session,
            documents.c.number,
            'BH-MAIN-POS01-2026-',
        )

    assert generated == 'BH-MAIN-POS01-2026-000010'
