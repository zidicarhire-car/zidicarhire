import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Stack, useLocalSearchParams } from 'expo-router';
import { useRef, useState } from 'react';

import { ChatThread } from '@/components/chat-thread';
import { Row, Text } from '@/components/ui';
import { get, post } from '@/lib/api';
import type { ChatMessage } from '@/lib/types';
import { useStaff } from '@/state/staff';
import { space, useColors } from '@/theme';

type Thread = { messages: ChatMessage[]; name: string; contact: string; city: string };

export default function StaffChat() {
  const c = useColors();
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const staff = useStaff();
  const qc = useQueryClient();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState('');
  const lastId = useRef(0);

  function add(list: ChatMessage[]) {
    if (!list.length) return;
    lastId.current = Math.max(lastId.current, ...list.map((m) => m.id));
    setMessages((old) => {
      const seen = new Set(old.map((m) => m.id));
      return [...old, ...list.filter((m) => !seen.has(m.id))];
    });
  }

  const thread = useQuery({
    queryKey: ['staff', 'chat', id],
    refetchInterval: 3000,
    queryFn: () => staff.call(async (token) => {
      const res = await get<Thread>(`staff/chats/${id}/messages/`, { token, params: { after: lastId.current } });
      add(res.messages);
      if (res.messages.length) qc.invalidateQueries({ queryKey: ['staff', 'chats'] });
      return res;
    }),
  });

  async function reply(body: string) {
    setError('');
    try {
      const res = await staff.call((token) => post<{ message: ChatMessage }>(`staff/chats/${id}/reply/`, { body }, { token }));
      add([res.message]);
      qc.invalidateQueries({ queryKey: ['staff', 'chats'] });
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }

  const info = thread.data;
  return (
    <>
      <Stack.Screen options={{ title: info?.name ?? name ?? 'Chat' }} />
      <ChatThread
        messages={messages}
        mine={(m) => m.sender !== 'visitor'}
        onSend={reply}
        error={error}
        placeholder="Type your reply"
        header={info && (info.contact || info.city) ? (
          <Row style={{ paddingHorizontal: space.lg, paddingVertical: space.sm, backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.border }}>
            <Text variant="muted" style={{ flex: 1 }}>{[info.contact, info.city].filter(Boolean).join(' · ')}</Text>
          </Row>
        ) : null}
      />
    </>
  );
}
