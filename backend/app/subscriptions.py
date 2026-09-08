from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Subscription, SubscriptionPlan, User


SUBSCRIPTION_WARNING_DAYS = 7
DEFAULT_GRACE_DAYS = 7
ALLOWED_STATES = {'ACTIVE', 'EXPIRING_SOON', 'GRACE'}


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def grace_end(subscription: Subscription) -> datetime:
    value = subscription.grace_ends_at
    return utc(value) if value is not None else utc(subscription.ends_at) + timedelta(days=DEFAULT_GRACE_DAYS)


@dataclass(frozen=True)
class SubscriptionLifecycle:
    subscription: Subscription | None
    plan: SubscriptionPlan | None
    state: str
    grace_ends_at: datetime | None
    days_remaining: int | None
    grace_days_remaining: int | None
    login_allowed: bool
    message: str


def subscription_lifecycle(tenant_id: str, session: Session, now: datetime | None = None) -> SubscriptionLifecycle:
    current = utc(now or datetime.now(UTC))
    subscription = session.scalar(
        select(Subscription)
        .where(Subscription.tenant_id == tenant_id)
        .order_by(Subscription.ends_at.desc())
    )
    if subscription is None:
        return SubscriptionLifecycle(None, None, 'EXPIRED', None, None, None, False,
                                     'No active subscription is available. Please contact the platform administrator.')

    plan = session.get(SubscriptionPlan, subscription.plan_id)
    end = utc(subscription.ends_at)
    grace = grace_end(subscription)
    starts = utc(subscription.starts_at)
    if subscription.status != 'ACTIVE':
        return SubscriptionLifecycle(subscription, plan, 'EXPIRED', grace, None, None, False,
                                     'This subscription is inactive. Please renew it to continue.')
    if starts > current:
        return SubscriptionLifecycle(subscription, plan, 'NOT_STARTED', grace, None, None, False,
                                     f'This subscription starts on {starts:%d %b %Y, %I:%M %p UTC}.')
    if current < end:
        days = max(1, math.ceil((end - current).total_seconds() / 86400))
        if end - current <= timedelta(days=SUBSCRIPTION_WARNING_DAYS):
            return SubscriptionLifecycle(subscription, plan, 'EXPIRING_SOON', grace, days, None, True,
                                         f'Your subscription expires in {days} day{"s" if days != 1 else ""}.')
        return SubscriptionLifecycle(subscription, plan, 'ACTIVE', grace, days, None, True, 'Subscription is active.')
    if current < grace:
        days = max(1, math.ceil((grace - current).total_seconds() / 86400))
        return SubscriptionLifecycle(subscription, plan, 'GRACE', grace, 0, days, True,
                                     f'Your subscription has expired. Renew within the {days}-day grace period to avoid service interruption.')
    return SubscriptionLifecycle(subscription, plan, 'EXPIRED', grace, 0, 0, False,
                                 'Your subscription and grace period have ended. Renewal is required to sign in.')


def subscription_error(lifecycle: SubscriptionLifecycle) -> HTTPException:
    sub = lifecycle.subscription
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            'code': 'SUBSCRIPTION_RENEWAL_REQUIRED',
            'message': lifecycle.message,
            'subscription_state': lifecycle.state,
            'subscription_end': utc(sub.ends_at).isoformat() if sub else None,
            'grace_ends_at': lifecycle.grace_ends_at.isoformat() if lifecycle.grace_ends_at else None,
            'renewal_path': '/subscribe',
        },
    )


def require_subscription_access(user: User, session: Session) -> SubscriptionLifecycle | None:
    if user.role_code == 'SUPER_ADMIN':
        return None
    lifecycle = subscription_lifecycle(user.tenant_id, session)
    if not lifecycle.login_allowed:
        raise subscription_error(lifecycle)
    return lifecycle


def active_subscription(user: User, session: Session) -> tuple[Subscription, SubscriptionPlan]:
    lifecycle = subscription_lifecycle(user.tenant_id, session)
    if (not lifecycle.login_allowed and user.role_code != 'SUPER_ADMIN') or lifecycle.subscription is None:
        raise subscription_error(lifecycle)
    if lifecycle.plan is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Subscription plan is unavailable.')
    return lifecycle.subscription, lifecycle.plan
