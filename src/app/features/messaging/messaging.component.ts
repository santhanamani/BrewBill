import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { BrewBillApiService } from '../../core/brew-bill-api.service';
import { TenantMessage, TenantMessageUser } from '../../core/models/api.models';
import { SessionService } from '../../core/session.service';
import { timedSignal } from '../../core/timed-signal';

interface ChatConversation {
  id: string;
  title: string;
  subtitle: string;
  avatar: string;
  group: boolean;
  unread: number;
  lastMessage: TenantMessage | null;
}

@Component({
  selector: 'app-messaging',
  imports: [FormsModule],
  templateUrl: './messaging.component.html',
  styleUrl: './messaging.component.css',
})
export class MessagingComponent implements OnDestroy {
  private readonly api = inject(BrewBillApiService);
  readonly session = inject(SessionService);
  readonly received = signal<TenantMessage[]>([]);
  readonly sent = signal<TenantMessage[]>([]);
  readonly users = signal<TenantMessageUser[]>([]);
  readonly selectedConversationId = signal('');
  readonly conversationSearch = signal('');
  readonly newChatOpen = signal(false);
  readonly newChatSearch = signal('');
  readonly replyingTo = signal<TenantMessage | null>(null);
  readonly reactionPickerId = signal('');
  readonly composerEmojiOpen = signal(false);
  readonly emojis = ['😀', '😂', '😍', '👍', '🙏', '🎉', '❤️', '😮', '😢', '☕'];
  readonly reactionEmojis = ['👍', '❤️', '😂', '😮', '😢', '🙏'];
  readonly loading = signal(true);
  readonly sending = signal(false);
  readonly error = signal('');
  readonly notice = timedSignal();
  messageBody = '';
  private readonly refreshTimer: number;

  readonly messages = computed(() => {
    const currentUserId = this.session.user()?.id;
    const seen = new Set<string>();
    return [...this.received(), ...this.sent()]
      .filter((message) => {
        const key = message.group_message_id
          ? `GROUP:${message.group_message_id}`
          : message.audience === 'GROUP' && message.sender_user_id === currentUserId
          ? `GROUP:${message.sender_user_id}:${message.created_at}:${message.subject}:${message.body}`
          : message.id;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort((left, right) => new Date(left.created_at).getTime() - new Date(right.created_at).getTime());
  });

  readonly directory = computed<ChatConversation[]>(() => {
    const groupMessages = this.messages().filter((message) => message.audience === 'GROUP');
    const group: ChatConversation = {
      id: 'GROUP',
      title: `${this.session.context()?.tenant_name ?? 'Tenant'} Group`,
      subtitle: `${this.users().length + 1} members`,
      avatar: 'groups',
      group: true,
      unread: this.received().filter((message) => message.audience === 'GROUP' && !message.read_at).length,
      lastMessage: groupMessages.at(-1) ?? null,
    };
    const direct = this.users().map((user): ChatConversation => {
      const messages = this.messages().filter((message) =>
        message.audience === 'DIRECT' &&
        (message.sender_user_id === user.id || message.recipient_user_id === user.id),
      );
      return {
        id: user.id,
        title: user.display_name,
        subtitle: `${this.roleLabel(user.role_code)} · @${user.username}`,
        avatar: this.initials(user.display_name),
        group: false,
        unread: this.received().filter((message) =>
          message.audience === 'DIRECT' && message.sender_user_id === user.id && !message.read_at,
        ).length,
        lastMessage: messages.at(-1) ?? null,
      };
    });
    return [group, ...direct];
  });

  readonly conversations = computed<ChatConversation[]>(() => {
    const query = this.conversationSearch().trim().toLowerCase();
    return this.directory().filter((conversation) => conversation.lastMessage).filter((conversation) =>
      !query || `${conversation.title} ${conversation.subtitle} ${conversation.lastMessage?.body ?? ''}`.toLowerCase().includes(query),
    );
  });

  readonly newChatOptions = computed(() => {
    const query = this.newChatSearch().trim().toLowerCase();
    return this.directory().filter((conversation) =>
      !query || `${conversation.title} ${conversation.subtitle}`.toLowerCase().includes(query),
    );
  });

  readonly activeConversation = computed(() =>
    this.directory().find((conversation) => conversation.id === this.selectedConversationId()) ?? null,
  );

  readonly threadMessages = computed(() => {
    const conversationId = this.selectedConversationId();
    return this.messages().filter((message) => conversationId === 'GROUP'
      ? message.audience === 'GROUP'
      : message.audience === 'DIRECT' &&
        (message.sender_user_id === conversationId || message.recipient_user_id === conversationId));
  });

  readonly totalUnread = computed(() => this.received().filter((message) => !message.read_at).length);

  constructor() {
    void this.load();
    this.refreshTimer = window.setInterval(() => void this.load(false), 5000);
  }

  ngOnDestroy(): void {
    window.clearInterval(this.refreshTimer);
  }

  private token(): string {
    const token = this.session.accessToken();
    if (!token) throw new Error('Sign in again to use tenant messages.');
    return token;
  }

  async load(showLoading = true): Promise<void> {
    if (showLoading) this.loading.set(true);
    this.error.set('');
    try {
      const [received, sent, users] = await Promise.all([
        this.api.listMessages(this.token()),
        this.api.listSentMessages(this.token()),
        this.api.listMessageUsers(this.token()),
      ]);
      this.received.set(received);
      this.sent.set(sent);
      this.users.set(users.filter((user) => user.id !== this.session.user()?.id));
      if (!this.directory().some((conversation) => conversation.id === this.selectedConversationId())) {
        this.selectedConversationId.set(this.conversations()[0]?.id ?? '');
      }
      await this.markActiveConversationRead();
      if (showLoading) this.scrollToLatest();
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to load tenant messages.');
    } finally {
      if (showLoading) this.loading.set(false);
    }
  }

  async selectConversation(conversationId: string): Promise<void> {
    this.selectedConversationId.set(conversationId);
    this.newChatOpen.set(false);
    this.newChatSearch.set('');
    this.replyingTo.set(null);
    this.reactionPickerId.set('');
    this.composerEmojiOpen.set(false);
    this.error.set('');
    await this.markActiveConversationRead();
    this.scrollToLatest();
  }

  openNewChat(): void {
    this.newChatSearch.set('');
    this.newChatOpen.set(true);
    window.setTimeout(() => document.querySelector<HTMLInputElement>('.new-chat-search input')?.focus());
  }

  private async markActiveConversationRead(): Promise<void> {
    const conversationId = this.selectedConversationId();
    const unread = this.received().filter((message) => !message.read_at && (conversationId === 'GROUP'
      ? message.audience === 'GROUP'
      : message.audience === 'DIRECT' && message.sender_user_id === conversationId));
    if (!unread.length) return;
    try {
      const updated = await Promise.all(unread.map((message) => this.api.markMessageRead(this.token(), message.id)));
      const byId = new Map(updated.map((message) => [message.id, message]));
      this.received.update((messages) => messages.map((message) => byId.get(message.id) ?? message));
    } catch {
      // A later five-second refresh retries read receipts without blocking the chat.
    }
  }

  async send(): Promise<void> {
    const body = this.messageBody.trim();
    const conversation = this.activeConversation();
    if (!body) {
      this.error.set('Type a message before sending.');
      return;
    }
    if (!conversation) {
      this.error.set('Choose a user or the tenant group.');
      return;
    }
    this.sending.set(true);
    this.error.set('');
    try {
      const result = await this.api.sendMessage(this.token(), {
        audience: conversation.group ? 'GROUP' : 'DIRECT',
        recipient_user_id: conversation.group ? null : conversation.id,
        subject: conversation.group ? 'Tenant group chat' : `Chat with ${conversation.title}`,
        body,
        reply_to_id: this.replyingTo()?.id ?? null,
      });
      this.messageBody = '';
      this.replyingTo.set(null);
      this.composerEmojiOpen.set(false);
      this.notice.set(conversation.group ? `Sent to ${result.delivered} group members.` : 'Message sent.');
      await this.load(false);
      this.scrollToLatest();
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to send message.');
    } finally {
      this.sending.set(false);
    }
  }

  startReply(message: TenantMessage): void {
    this.replyingTo.set(message);
    this.reactionPickerId.set('');
    window.setTimeout(() => document.querySelector<HTMLTextAreaElement>('.chat-composer textarea')?.focus());
  }

  appendEmoji(emoji: string): void {
    this.messageBody += emoji;
    this.composerEmojiOpen.set(false);
    window.setTimeout(() => document.querySelector<HTMLTextAreaElement>('.chat-composer textarea')?.focus());
  }

  async react(message: TenantMessage, emoji: string): Promise<void> {
    this.reactionPickerId.set('');
    this.error.set('');
    try {
      await this.api.reactToMessage(this.token(), message.id, emoji);
      await this.load(false);
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to react to this message.');
    }
  }

  messageKey(message: TenantMessage): string {
    return message.group_message_id ?? message.id;
  }

  jumpToMessage(reply: TenantMessage): void {
    const directKey = reply.reply_to_group_message_id ?? reply.reply_to_id;
    let target = directKey ? document.getElementById(`message-${directKey}`) : null;
    if (!target) {
      const replyTime = new Date(reply.created_at).getTime();
      const referenced = this.threadMessages()
        .filter((candidate) => candidate.id !== reply.id)
        .filter((candidate) => {
          if (candidate.id === reply.reply_to_id) return true;
          if (reply.reply_to_group_message_id && candidate.group_message_id === reply.reply_to_group_message_id) return true;
          return Boolean(
            reply.reply_to_body &&
            candidate.body === reply.reply_to_body &&
            candidate.sender_name === reply.reply_to_sender_name &&
            new Date(candidate.created_at).getTime() <= replyTime
          );
        })
        .at(-1);
      target = referenced ? document.getElementById(`message-${this.messageKey(referenced)}`) : null;
    }
    if (!target) {
      this.notice.set('The referenced message is outside the loaded history.');
      return;
    }
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.add('message-highlight');
    window.setTimeout(() => target.classList.remove('message-highlight'), 1600);
  }

  onComposerKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void this.send();
    }
  }

  isMine(message: TenantMessage): boolean {
    return message.sender_user_id === this.session.user()?.id;
  }

  showSubject(message: TenantMessage): boolean {
    return !message.subject.startsWith('Chat with ') && message.subject !== 'Tenant group chat';
  }

  startsNewDay(index: number): boolean {
    if (index === 0) return true;
    return this.dayKey(this.threadMessages()[index - 1].created_at) !== this.dayKey(this.threadMessages()[index].created_at);
  }

  dayLabel(value: string): string {
    const date = new Date(value);
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);
    if (this.dayKey(value) === this.dayKey(today.toISOString())) return 'Today';
    if (this.dayKey(value) === this.dayKey(yesterday.toISOString())) return 'Yesterday';
    return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
  }

  messageTime(value: string): string {
    return new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit' }).format(new Date(value));
  }

  conversationTime(message: TenantMessage | null): string {
    if (!message) return '';
    const date = new Date(message.created_at);
    if (this.dayKey(message.created_at) === this.dayKey(new Date().toISOString())) return this.messageTime(message.created_at);
    return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short' }).format(date);
  }

  preview(message: TenantMessage | null): string {
    if (!message) return 'Start a conversation';
    return `${this.isMine(message) ? 'You: ' : ''}${message.body.replace(/\s+/g, ' ')}`;
  }

  initials(name: string): string {
    return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || 'U';
  }

  private roleLabel(role: string): string {
    return role.toLowerCase().split('_').map((part) => part[0].toUpperCase() + part.slice(1)).join(' ');
  }

  private dayKey(value: string): string {
    const parts = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit' })
      .formatToParts(new Date(value));
    const valueFor = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
    return `${valueFor('year')}-${valueFor('month')}-${valueFor('day')}`;
  }

  private scrollToLatest(): void {
    window.setTimeout(() => {
      const thread = document.querySelector<HTMLElement>('.chat-thread');
      thread?.scrollTo({ top: thread.scrollHeight, behavior: 'smooth' });
      document.querySelector<HTMLTextAreaElement>('.chat-composer textarea')?.focus();
    });
  }
}
