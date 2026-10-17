/** Message bubbles and a message box, shared by the customer chat and the staff inbox. */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { FlatList, KeyboardAvoidingView, Platform, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { IconButton, Text } from '@/components/ui';
import type { ChatMessage } from '@/lib/types';
import { fonts, radius, space, useColors } from '@/theme';

export function ChatThread({ messages, mine, onSend, placeholder = 'Type a message', header, footer, error }: {
  messages: ChatMessage[];
  /** Which sender is "me" (right-hand, indigo bubbles). */
  mine: (m: ChatMessage) => boolean;
  onSend: (text: string) => Promise<void>;
  placeholder?: string;
  header?: ReactNode;
  footer?: ReactNode;
  error?: string;
}) {
  const c = useColors();
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const list = useRef<FlatList<ChatMessage>>(null);

  useEffect(() => {
    const t = setTimeout(() => list.current?.scrollToEnd({ animated: true }), 50);
    return () => clearTimeout(t);
  }, [messages.length]);

  async function send() {
    const body = text.trim();
    if (!body || sending) return;
    setText('');
    setSending(true);
    try {
      await onSend(body);
    } catch {
      setText(body);   // keep what they typed so it can be sent again
    } finally {
      setSending(false);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}>
      {header}
      <FlatList
        ref={list}
        data={messages}
        keyExtractor={(m) => String(m.id)}
        contentContainerStyle={{ padding: space.lg, gap: space.sm }}
        renderItem={({ item }) => {
          const me = mine(item);
          return (
            <View style={{
              alignSelf: me ? 'flex-end' : 'flex-start', maxWidth: '84%', paddingHorizontal: space.md, paddingVertical: space.sm,
              borderRadius: 16, borderBottomRightRadius: me ? 4 : 16, borderBottomLeftRadius: me ? 16 : 4,
              backgroundColor: me ? c.brand : c.surface, borderWidth: me ? 0 : 1, borderColor: c.border,
              borderStyle: item.sender === 'bot' ? 'dashed' : 'solid',
            }}>
              {item.label ? <Text variant="small" color={me ? c.onBrandMuted : c.muted} style={{ fontSize: 12 }}>{item.label}</Text> : null}
              <Text color={me ? c.onBrand : c.text} selectable>{item.body}</Text>
              <Text variant="small" color={me ? c.onBrandMuted : c.muted} style={{ fontSize: 11, alignSelf: 'flex-end' }}>{item.time}</Text>
            </View>
          );
        }}
      />
      {error ? <Text variant="small" color={c.danger} style={{ paddingHorizontal: space.lg }}>{error}</Text> : null}
      {footer}
      <SafeAreaView edges={['bottom']} style={{ backgroundColor: c.surface, borderTopWidth: 1, borderTopColor: c.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: space.sm, padding: space.sm }}>
          <TextInput value={text} onChangeText={setText} placeholder={placeholder} placeholderTextColor={c.muted} multiline maxLength={1000}
            accessibilityLabel="Message"
            style={{ flex: 1, minHeight: 44, maxHeight: 120, borderWidth: 1.5, borderColor: c.controlBorder, borderRadius: radius.md,
              paddingHorizontal: space.md, paddingTop: 11, fontSize: 16, fontFamily: fonts.regular, color: c.text, backgroundColor: c.bg }} />
          <View style={{ backgroundColor: c.primary, borderRadius: radius.md, opacity: text.trim() && !sending ? 1 : 0.5 }}>
            <IconButton icon="send" label="Send message" color={c.onPrimary} onPress={send} />
          </View>
        </View>
      </SafeAreaView>
    </KeyboardAvoidingView>
  );
}
