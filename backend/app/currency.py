from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import Currency, Tenant
from .schemas import CurrencyRead


DEFAULT_CURRENCY_CODE = 'INR'
DEFAULT_CURRENCY = Currency(
    code='INR', name='Indian Rupee', symbol='₹', locale='en-IN', decimal_places=2, is_active=True
)


def resolve_currency(session: Session, code: str | None) -> Currency:
    normalized = (code or DEFAULT_CURRENCY_CODE).strip().upper()
    currency = session.get(Currency, normalized)
    if currency is None and normalized == DEFAULT_CURRENCY_CODE:
        return DEFAULT_CURRENCY
    if currency is None or not currency.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='The selected currency is not available.',
        )
    return currency


def tenant_currency(session: Session, tenant: Tenant) -> Currency:
    currency = session.get(Currency, tenant.currency_code or DEFAULT_CURRENCY_CODE)
    if currency is None:
        currency = session.get(Currency, DEFAULT_CURRENCY_CODE) or DEFAULT_CURRENCY
    return currency


def currency_read(currency: Currency) -> CurrencyRead:
    return CurrencyRead.model_validate(currency)
