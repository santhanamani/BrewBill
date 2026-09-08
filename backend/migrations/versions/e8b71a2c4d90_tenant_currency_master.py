# Tenant currency master.

from alembic import op
import sqlalchemy as sa

revision = 'e8b71a2c4d90'
down_revision = 'c4b1f7d92e30'
branch_labels = None
depends_on = None

CURRENCIES = [
    ('AED', 'UAE Dirham', 'AED', 'ar-AE', 2),
    ('AUD', 'Australian Dollar', 'A$', 'en-AU', 2),
    ('BDT', 'Bangladeshi Taka', 'Tk', 'bn-BD', 2),
    ('BHD', 'Bahraini Dinar', 'BHD', 'ar-BH', 3),
    ('BRL', 'Brazilian Real', 'R$', 'pt-BR', 2),
    ('CAD', 'Canadian Dollar', 'CA$', 'en-CA', 2),
    ('CHF', 'Swiss Franc', 'CHF', 'de-CH', 2),
    ('CNY', 'Chinese Yuan', 'CN¥', 'zh-CN', 2),
    ('CZK', 'Czech Koruna', 'Kc', 'cs-CZ', 2),
    ('DKK', 'Danish Krone', 'kr', 'da-DK', 2),
    ('EGP', 'Egyptian Pound', 'E£', 'ar-EG', 2),
    ('EUR', 'Euro', '€', 'en-IE', 2),
    ('GBP', 'British Pound', '£', 'en-GB', 2),
    ('HKD', 'Hong Kong Dollar', 'HK$', 'zh-HK', 2),
    ('HUF', 'Hungarian Forint', 'Ft', 'hu-HU', 2),
    ('IDR', 'Indonesian Rupiah', 'Rp', 'id-ID', 2),
    ('ILS', 'Israeli New Shekel', 'ILS', 'he-IL', 2),
    ('INR', 'Indian Rupee', '₹', 'en-IN', 2),
    ('JPY', 'Japanese Yen', '¥', 'ja-JP', 0),
    ('KES', 'Kenyan Shilling', 'KSh', 'en-KE', 2),
    ('KRW', 'South Korean Won', 'KRW', 'ko-KR', 0),
    ('KWD', 'Kuwaiti Dinar', 'KWD', 'ar-KW', 3),
    ('LKR', 'Sri Lankan Rupee', 'Rs', 'si-LK', 2),
    ('MYR', 'Malaysian Ringgit', 'RM', 'ms-MY', 2),
    ('NGN', 'Nigerian Naira', '₦', 'en-NG', 2),
    ('NOK', 'Norwegian Krone', 'kr', 'nb-NO', 2),
    ('NPR', 'Nepalese Rupee', 'Rs', 'ne-NP', 2),
    ('NZD', 'New Zealand Dollar', 'NZ$', 'en-NZ', 2),
    ('OMR', 'Omani Rial', 'OMR', 'ar-OM', 3),
    ('PHP', 'Philippine Peso', '₱', 'en-PH', 2),
    ('PKR', 'Pakistani Rupee', 'Rs', 'ur-PK', 2),
    ('PLN', 'Polish Zloty', 'zl', 'pl-PL', 2),
    ('QAR', 'Qatari Riyal', 'QAR', 'ar-QA', 2),
    ('SAR', 'Saudi Riyal', 'SAR', 'ar-SA', 2),
    ('SEK', 'Swedish Krona', 'kr', 'sv-SE', 2),
    ('SGD', 'Singapore Dollar', 'S$', 'en-SG', 2),
    ('THB', 'Thai Baht', '฿', 'th-TH', 2),
    ('TRY', 'Turkish Lira', '₺', 'tr-TR', 2),
    ('USD', 'US Dollar', '$', 'en-US', 2),
    ('VND', 'Vietnamese Dong', '₫', 'vi-VN', 0),
    ('ZAR', 'South African Rand', 'R', 'en-ZA', 2),
]


def upgrade() -> None:
    table = op.create_table(
        'currencies',
        sa.Column('code', sa.String(length=3), primary_key=True),
        sa.Column('name', sa.String(length=120), nullable=False, unique=True),
        sa.Column('symbol', sa.String(length=12), nullable=False),
        sa.Column('locale', sa.String(length=24), nullable=False, server_default='en-US'),
        sa.Column('decimal_places', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index('ix_currencies_is_active', 'currencies', ['is_active'])
    op.bulk_insert(table, [
        {'code': code, 'name': name, 'symbol': symbol, 'locale': locale,
         'decimal_places': decimals, 'is_active': True}
        for code, name, symbol, locale, decimals in CURRENCIES
    ])
    op.add_column(
        'tenants',
        sa.Column('currency_code', sa.String(length=3), nullable=False, server_default='INR'),
    )
    op.create_index('ix_tenants_currency_code', 'tenants', ['currency_code'])
    op.create_foreign_key(
        'fk_tenants_currency_code', 'tenants', 'currencies', ['currency_code'], ['code']
    )


def downgrade() -> None:
    op.drop_constraint('fk_tenants_currency_code', 'tenants', type_='foreignkey')
    op.drop_index('ix_tenants_currency_code', table_name='tenants')
    op.drop_column('tenants', 'currency_code')
    op.drop_index('ix_currencies_is_active', table_name='currencies')
    op.drop_table('currencies')
