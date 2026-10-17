import { useQuery } from '@tanstack/react-query';
import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ScrollView, View } from 'react-native';

import { ChatThread } from '@/components/chat-thread';
import { Button, Chip, ErrorText, Field, Icon, Loading, Row, Screen, Text } from '@/components/ui';
import { useConfig } from '@/hooks/use-config';
import { ApiError, get, post } from '@/lib/api';
import { saveChatId, savedChatId, savedCustomer } from '@/lib/storage';
import type { ChatMessage } from '@/lib/types';
import { useSearch } from '@/state/search';
import { space, useColors } from '@/theme';

const QUICK = [
  ['Prices', 'What are your prices?'],
  ['How to book', 'How do I book a car?'],
  ['Payment', 'How do I pay?'],
  ['Documents', 'What documents do I need?'],
  ['Pick-up places', 'Where can I pick up the car?'],
];

type Messages = { messages: ChatMessage[]; agent_online: boolean; wants_agent: boolean };

export default function Chat() {
  const c = useColors();
  const [focused, setFocused] = useState(true);
  useFocusEffect(useCallback(() => { setFocused(true); return () => setFocused(false); }, []));
  const { data: config } = useConfig();
  const search = useSearch();
  const [chatId, setChatId] = useState<string | null | undefined>(undefined);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [wantsAgent, setWantsAgent] = useState(false);
  const [error, setError] = useState('');
  const lastId = useRef(0);

  // Intro form
  const [name, setName] = useState('');
  const [contact, setContact] = useState('');
  const [city, setCity] = useState(search.city);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    savedChatId().then((id) => setChatId(id));
    savedCustomer().then((s) => { setName(s.name); setContact(s.phone || s.email); });
  }, []);

  function add(list: ChatMessage[]) {
    if (!list.length) return;
    lastId.current = Math.max(lastId.current, ...list.map((m) => m.id));
    setMessages((old) => {
      const seen = new Set(old.map((m) => m.id));
      return [...old, ...list.filter((m) => !seen.has(m.id))];
    });
  }

  const poll = useQuery({
    queryKey: ['chat', chatId],
    enabled: !!chatId,
    refetchInterval: focused ? 3000 : 20000,
    queryFn: async () => {
      try {
        const res = await get<Messages>(`chat/${chatId}/messages/`, { params: { after: lastId.current } });
        add(res.messages);
        if (res.wants_agent) setWantsAgent(true);
        if (res.messages.some((m) => m.sender === 'admin')) setWantsAgent(false);
        return res;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) { await saveChatId(null); setChatId(null); }
        throw err;
      }
    },
  });

  async function start() {
    setError('');
    setStarting(true);
    try {
      const res = await post<{ id: string }>('chat/', { name, contact, city });
      await saveChatId(res.id);
      setChatId(res.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setStarting(false);
    }
  }

  async function send(body: string) {
    setError('');
    try {
      const res = await post<{ message: ChatMessage; replies: ChatMessage[]; wants_agent: boolean }>(`chat/${chatId}/send/`, { body });
      add([res.message, ...res.replies]);
      if (res.wants_agent) setWantsAgent(true);
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }

  async function askPerson() {
    try {
      const res = await post<{ replies: ChatMessage[] }>(`chat/${chatId}/agent/`);
      add(res.replies);
      setWantsAgent(true);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (chatId === undefined) return <Loading />;

  if (!chatId) {
    return (
      <Screen>
        <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: c.tint, alignItems: 'center', justifyContent: 'center' }}>
          <Icon name="chatbubbles-outline" size={26} />
        </View>
        <Text variant="title">Chat with us</Text>
        <Text variant="muted">Get instant answers about prices, booking and payment, or talk to our team. Tell us who you are so we can follow up.</Text>
        <Field label="Your name" value={name} onChangeText={setName} autoComplete="name" />
        <Field label="Phone or email (optional)" value={contact} onChangeText={setContact} autoCapitalize="none" />
        <Text variant="label">Which city? (optional)</Text>
        <Row style={{ flexWrap: 'wrap' }}>
          <Chip label="Not sure yet" selected={!city} onPress={() => setCity('')} />
          {(config?.branches ?? []).map((b) => <Chip key={b.slug} label={b.name} selected={city === b.slug} onPress={() => setCity(b.slug)} />)}
        </Row>
        <ErrorText>{error}</ErrorText>
        <Button title="Start chat" icon="chatbubbles-outline" size="lg" loading={starting} disabled={name.trim().length < 2} onPress={start} />
      </Screen>
    );
  }

  return (
    <ChatThread
      messages={messages}
      mine={(m) => m.sender === 'visitor'}
      onSend={send}
      error={error}
      header={
        <Row style={{ paddingHorizontal: space.lg, paddingVertical: space.sm, backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.border }}>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: poll.data?.agent_online ? '#5BD46A' : c.muted }} />
          <Text variant="muted">{poll.data?.agent_online ? 'Online now' : 'Instant answers, or a person during opening hours'}</Text>
        </Row>
      }
      footer={
        <ScrollView horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ gap: space.sm, paddingHorizontal: space.lg, paddingVertical: space.sm }}>
          <Chip label={wantsAgent ? 'Team member requested' : 'Talk to a person'} selected={!wantsAgent} icon="person-outline"
            onPress={wantsAgent ? undefined : askPerson} />
          {QUICK.map(([label, ask]) => <Chip key={label} label={label} onPress={() => { send(ask).catch(() => {}); }} />)}
        </ScrollView>
      }
    />
  );
}
