from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import require_role
from ..database import get_session
from ..models import Role, TenantMessage, TenantMessageReaction, User
from ..schemas import (
    TenantMessageCreate,
    TenantMessageReactionUpdate,
    TenantMessageRead,
    TenantMessageSendResult,
    TenantMessageUserRead,
)
from ..subscriptions import require_plan_feature


router = APIRouter(prefix='/api/messages', tags=['tenant-messages'])
ALLOWED_REACTIONS = {'👍', '❤️', '😂', '😮', '😢', '🙏'}


def require_messaging(user: User, session: Session) -> None:
    require_plan_feature(user, session, 'tenant_messaging')


def message_reads(rows: list[TenantMessage], user: User, session: Session) -> list[TenantMessageRead]:
    if not rows:
        return []
    group_ids = {row.group_message_id for row in rows if row.group_message_id}
    sibling_rows = session.execute(
        select(TenantMessage.id, TenantMessage.group_message_id).where(
            TenantMessage.tenant_id == user.tenant_id,
            TenantMessage.group_message_id.in_(group_ids),
        )
    ).all() if group_ids else []
    sibling_ids: dict[str, set[str]] = {group_id: set() for group_id in group_ids}
    for message_id, group_id in sibling_rows:
        sibling_ids[group_id].add(message_id)
    all_message_ids = {row.id for row in rows}
    all_message_ids.update(message_id for ids in sibling_ids.values() for message_id in ids)
    reactions = session.scalars(select(TenantMessageReaction).where(
        TenantMessageReaction.tenant_id == user.tenant_id,
        TenantMessageReaction.message_id.in_(all_message_ids),
    )).all()
    message_key_by_id = {row.id: row.group_message_id or row.id for row in rows}
    for group_id, ids in sibling_ids.items():
        message_key_by_id.update({message_id: group_id for message_id in ids})
    reaction_summary: dict[str, dict[str, dict[str, object]]] = {}
    for reaction in reactions:
        key = message_key_by_id.get(reaction.message_id, reaction.message_id)
        emoji = reaction_summary.setdefault(key, {}).setdefault(
            reaction.emoji, {'count': 0, 'reacted_by_me': False},
        )
        emoji['count'] = int(emoji['count']) + 1
        if reaction.user_id == user.id:
            emoji['reacted_by_me'] = True

    reply_ids = {row.reply_to_id for row in rows if row.reply_to_id}
    reply_rows = {
        row.id: row for row in session.scalars(select(TenantMessage).where(
            TenantMessage.tenant_id == user.tenant_id,
            TenantMessage.id.in_(reply_ids),
        )).all()
    } if reply_ids else {}
    user_ids = {value for row in rows for value in (row.sender_user_id, row.recipient_user_id)}
    user_ids.update(reply.sender_user_id for reply in reply_rows.values())
    users = {row.id: row for row in session.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}

    result: list[TenantMessageRead] = []
    for row in rows:
        reply = reply_rows.get(row.reply_to_id) if row.reply_to_id else None
        key = row.group_message_id or row.id
        result.append(TenantMessageRead(
            id=row.id,
            group_message_id=row.group_message_id,
            sender_user_id=row.sender_user_id,
            sender_name=users[row.sender_user_id].display_name if row.sender_user_id in users else 'Tenant user',
            recipient_user_id=row.recipient_user_id,
            recipient_name=users[row.recipient_user_id].display_name if row.recipient_user_id in users else 'Tenant user',
            audience=row.audience,
            subject=row.subject,
            body=row.body,
            reply_to_id=row.reply_to_id,
            reply_to_group_message_id=reply.group_message_id if reply else None,
            reply_to_sender_name=users[reply.sender_user_id].display_name if reply and reply.sender_user_id in users else None,
            reply_to_body=reply.body if reply else None,
            reactions=[
                {'emoji': emoji, 'count': values['count'], 'reacted_by_me': values['reacted_by_me']}
                for emoji, values in reaction_summary.get(key, {}).items()
            ],
            read_at=row.read_at,
            created_at=row.created_at,
        ))
    return result


def visible_message(message_id: str, user: User, session: Session) -> TenantMessage:
    row = session.scalar(select(TenantMessage).where(
        TenantMessage.id == message_id,
        TenantMessage.tenant_id == user.tenant_id,
        (TenantMessage.sender_user_id == user.id) | (TenantMessage.recipient_user_id == user.id),
    ))
    if row is None:
        raise HTTPException(status_code=404, detail='Message not found.')
    return row


@router.get('/users', response_model=list[TenantMessageUserRead])
def message_users(
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> list[TenantMessageUserRead]:
    require_messaging(user, session)
    users = session.scalars(
        select(User)
        .where(User.tenant_id == user.tenant_id, User.is_active.is_(True), User.role.has(Role.code != 'SUPER_ADMIN'))
        .order_by(User.display_name)
    ).all()
    return [TenantMessageUserRead(id=row.id, display_name=row.display_name, username=row.username, role_code=row.role_code) for row in users]


@router.get('', response_model=list[TenantMessageRead])
def inbox(
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> list[TenantMessageRead]:
    require_messaging(user, session)
    rows = session.scalars(
        select(TenantMessage)
        .where(TenantMessage.tenant_id == user.tenant_id, TenantMessage.recipient_user_id == user.id)
        .order_by(TenantMessage.created_at.desc())
        .limit(250)
    ).all()
    return message_reads(list(rows), user, session)


@router.get('/sent', response_model=list[TenantMessageRead])
def sent_messages(
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> list[TenantMessageRead]:
    require_messaging(user, session)
    rows = session.scalars(
        select(TenantMessage)
        .where(TenantMessage.tenant_id == user.tenant_id, TenantMessage.sender_user_id == user.id)
        .order_by(TenantMessage.created_at.desc())
        .limit(250)
    ).all()
    return message_reads(list(rows), user, session)


@router.post('', response_model=TenantMessageSendResult, status_code=status.HTTP_201_CREATED)
def send_message(
    body: TenantMessageCreate,
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> TenantMessageSendResult:
    require_messaging(user, session)
    if body.reply_to_id:
        visible_message(body.reply_to_id, user, session)
    active_users = session.scalars(
        select(User).where(User.tenant_id == user.tenant_id, User.is_active.is_(True), User.role.has(Role.code != 'SUPER_ADMIN'))
    ).all()
    if body.audience == 'GROUP':
        recipients = [row for row in active_users if row.id != user.id]
    else:
        recipients = [row for row in active_users if row.id == body.recipient_user_id and row.id != user.id]
        if not recipients:
            raise HTTPException(status_code=422, detail='Choose an active user from this tenant.')
    if not recipients:
        raise HTTPException(status_code=409, detail='There are no other active tenant users to receive this message.')
    group_message_id = str(uuid4()) if body.audience == 'GROUP' else None
    for recipient in recipients:
        session.add(TenantMessage(
            id=str(uuid4()), tenant_id=user.tenant_id, sender_user_id=user.id, recipient_user_id=recipient.id,
            group_message_id=group_message_id, reply_to_id=body.reply_to_id,
            audience=body.audience, subject=body.subject.strip(), body=body.body.strip(),
        ))
    session.commit()
    return TenantMessageSendResult(delivered=len(recipients))


@router.post('/{message_id}/read', response_model=TenantMessageRead)
def mark_read(
    message_id: str,
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> TenantMessageRead:
    require_messaging(user, session)
    row = visible_message(message_id, user, session)
    if row.recipient_user_id != user.id:
        raise HTTPException(status_code=404, detail='Message not found.')
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
    return message_reads([row], user, session)[0]


@router.post('/{message_id}/reactions', response_model=TenantMessageRead)
def react_to_message(
    message_id: str,
    body: TenantMessageReactionUpdate,
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> TenantMessageRead:
    require_messaging(user, session)
    if body.emoji not in ALLOWED_REACTIONS:
        raise HTTPException(status_code=422, detail='Unsupported message reaction.')
    row = visible_message(message_id, user, session)
    sibling_ids = [row.id]
    if row.group_message_id:
        sibling_ids = list(session.scalars(select(TenantMessage.id).where(
            TenantMessage.tenant_id == user.tenant_id,
            TenantMessage.group_message_id == row.group_message_id,
        )).all())
    existing = list(session.scalars(select(TenantMessageReaction).where(
        TenantMessageReaction.tenant_id == user.tenant_id,
        TenantMessageReaction.message_id.in_(sibling_ids),
        TenantMessageReaction.user_id == user.id,
    )).all())
    remove_only = any(reaction.emoji == body.emoji for reaction in existing)
    for reaction in existing:
        session.delete(reaction)
    if not remove_only:
        session.add(TenantMessageReaction(
            id=str(uuid4()), tenant_id=user.tenant_id, message_id=row.id,
            user_id=user.id, emoji=body.emoji,
        ))
    session.commit()
    return message_reads([row], user, session)[0]
