import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import Outlet, Role, Subscription, SubscriptionPlan, Tenant, User


def test_ultra_messages_are_delivered_only_inside_tenant() -> None:
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with sessions() as session:
        role = Role(id=str(uuid4()), code='ADMIN', name='Administrator')
        tenant = Tenant(id=str(uuid4()), code='MSG', name='Message Tenant', status='ACTIVE')
        other_tenant = Tenant(id=str(uuid4()), code='OTHER', name='Other Tenant', status='ACTIVE')
        outlet = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='MAAA', name='Main')
        other_outlet = Outlet(id=str(uuid4()), tenant_id=other_tenant.id, code='MAAB', name='Other')
        sender = User(id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=role.id, username='sender', display_name='Sender', password_hash='x', is_active=True)
        receiver = User(id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=role.id, username='receiver', display_name='Receiver', password_hash='x', is_active=True)
        manager = User(id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=role.id, username='manager', display_name='Manager', password_hash='x', is_active=True)
        outsider = User(id=str(uuid4()), tenant_id=other_tenant.id, outlet_id=other_outlet.id, role_id=role.id, username='outsider', display_name='Outsider', password_hash='x', is_active=True)
        sender.role = receiver.role = manager.role = outsider.role = role
        plan = SubscriptionPlan(id=str(uuid4()), code='ULTRA_PROFESSIONAL', name='Ultra', feature_json=json.dumps({'tenant_messaging': True}))
        other_plan = SubscriptionPlan(id=str(uuid4()), code='ULTRA_OTHER', name='Ultra Other', feature_json=json.dumps({'tenant_messaging': True}))
        session.add_all([role, tenant, other_tenant, outlet, other_outlet, sender, receiver, manager, outsider, plan, other_plan,
                         Subscription(id=str(uuid4()), tenant_id=tenant.id, plan_id=plan.id, status='ACTIVE', starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=30)),
                         Subscription(id=str(uuid4()), tenant_id=other_tenant.id, plan_id=other_plan.id, status='ACTIVE', starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=30))])
        session.commit()

    def test_session():
        with sessions() as session:
            yield session

    active_user = {'value': sender}
    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: active_user['value']
    try:
        with TestClient(app) as client:
            users = client.get('/api/messages/users')
            assert users.status_code == 200
            assert {row['id'] for row in users.json()} == {sender.id, receiver.id, manager.id}

            blocked = client.post('/api/messages', json={'audience': 'DIRECT', 'recipient_user_id': outsider.id, 'subject': 'Private', 'body': 'No cross tenant delivery'})
            assert blocked.status_code == 422

            sent = client.post('/api/messages', json={'audience': 'DIRECT', 'recipient_user_id': receiver.id, 'subject': 'Stock check', 'body': 'Please check milk stock.'})
            assert sent.status_code == 201
            assert sent.json()['delivered'] == 1

            sent_mailbox = client.get('/api/messages/sent')
            assert sent_mailbox.status_code == 200
            assert len(sent_mailbox.json()) == 1
            assert sent_mailbox.json()[0]['recipient_name'] == 'Receiver'
            assert sent_mailbox.json()[0]['body'] == 'Please check milk stock.'
            original_message_id = sent_mailbox.json()[0]['id']

            active_user['value'] = receiver
            inbox = client.get('/api/messages')
            assert inbox.status_code == 200
            assert len(inbox.json()) == 1
            assert inbox.json()[0]['sender_name'] == 'Sender'
            read = client.post(f"/api/messages/{inbox.json()[0]['id']}/read")
            assert read.status_code == 200
            assert read.json()['read_at'] is not None
            reaction = client.post(f"/api/messages/{original_message_id}/reactions", json={'emoji': '👍'})
            assert reaction.status_code == 200
            assert reaction.json()['reactions'] == [{'emoji': '👍', 'count': 1, 'reacted_by_me': True}]

            reply = client.post('/api/messages', json={
                'audience': 'DIRECT', 'recipient_user_id': sender.id,
                'subject': 'Re: Stock check', 'body': 'Milk stock is available.',
                'reply_to_id': original_message_id,
            })
            assert reply.status_code == 201

            active_user['value'] = sender
            sender_inbox = client.get('/api/messages')
            assert len(sender_inbox.json()) == 1
            assert sender_inbox.json()[0]['sender_name'] == 'Receiver'
            assert sender_inbox.json()[0]['body'] == 'Milk stock is available.'
            assert sender_inbox.json()[0]['reply_to_id'] == original_message_id
            assert sender_inbox.json()[0]['reply_to_sender_name'] == 'Sender'
            assert sender_inbox.json()[0]['reply_to_body'] == 'Please check milk stock.'
            original_for_sender = client.get('/api/messages/sent').json()[0]
            assert original_for_sender['reactions'] == [{'emoji': '👍', 'count': 1, 'reacted_by_me': False}]

            group = client.post('/api/messages', json={
                'audience': 'GROUP', 'recipient_user_id': None,
                'subject': 'Tenant group chat', 'body': 'The cafe closes at 10 PM today.',
            })
            assert group.status_code == 201
            assert group.json()['delivered'] == 2

            active_user['value'] = receiver
            group_inbox = client.get('/api/messages').json()
            group_messages = [row for row in group_inbox if row['audience'] == 'GROUP']
            assert len(group_messages) == 1
            assert group_messages[0]['body'] == 'The cafe closes at 10 PM today.'

            active_user['value'] = manager
            manager_group = [row for row in client.get('/api/messages').json() if row['audience'] == 'GROUP'][0]
            group_reaction = client.post(f"/api/messages/{manager_group['id']}/reactions", json={'emoji': '❤️'})
            assert group_reaction.status_code == 200

            active_user['value'] = sender
            sent_group_rows = [row for row in client.get('/api/messages/sent').json() if row['audience'] == 'GROUP']
            assert len(sent_group_rows) == 2
            assert all(row['reactions'] == [{'emoji': '❤️', 'count': 1, 'reacted_by_me': False}] for row in sent_group_rows)
            emoji_only = client.post('/api/messages', json={
                'audience': 'DIRECT', 'recipient_user_id': manager.id,
                'subject': 'Chat with Manager', 'body': '😀',
            })
            assert emoji_only.status_code == 201

            active_user['value'] = outsider
            assert client.get('/api/messages').json() == []
            assert client.post(f"/api/messages/{original_message_id}/reactions", json={'emoji': '👍'}).status_code == 404
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
