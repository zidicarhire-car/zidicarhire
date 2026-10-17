/** A small form in a bottom sheet, for actions that need input: a reason, an M-Pesa code, an amount. */
import { type ReactNode } from 'react';
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button, ErrorText, IconButton, Row, Text } from '@/components/ui';
import { radius, space, useColors } from '@/theme';

export function FormSheet({ visible, title, message, children, confirm, kind = 'primary', onConfirm, onClose, busy, error }: {
  visible: boolean;
  title: string;
  message?: string;
  children?: ReactNode;
  confirm: string;
  kind?: 'primary' | 'danger' | 'mpesa';
  onConfirm: () => void;
  onClose: () => void;
  busy?: boolean;
  error?: string;
}) {
  const c = useColors();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={{ flex: 1, backgroundColor: '#0A0D1E99' }} onPress={onClose} accessibilityLabel="Close" />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <SafeAreaView edges={['bottom']} style={{ backgroundColor: c.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg }}>
          <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.md }} keyboardShouldPersistTaps="handled">
            <Row style={{ justifyContent: 'space-between' }}>
              <Text variant="heading" style={{ flex: 1 }}>{title}</Text>
              <IconButton icon="close" label="Close" onPress={onClose} />
            </Row>
            {message ? <Text>{message}</Text> : null}
            {children}
            <ErrorText>{error}</ErrorText>
            <View style={{ flexDirection: 'row', gap: space.sm }}>
              <Button title="Go back" kind="ghost" onPress={onClose} style={{ flex: 1 }} />
              <Button title={confirm} kind={kind} onPress={onConfirm} loading={busy} style={{ flex: 1.4 }} />
            </View>
          </ScrollView>
        </SafeAreaView>
      </KeyboardAvoidingView>
    </Modal>
  );
}
