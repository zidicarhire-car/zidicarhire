import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { Button, ErrorText, Field, Icon, Screen, Text } from '@/components/ui';
import { useStaff } from '@/state/staff';
import { useColors } from '@/theme';

export default function StaffLogin() {
  const c = useColors();
  const staff = useStaff();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function signIn() {
    setError('');
    setBusy(true);
    try {
      await staff.signIn(username.trim(), password);
      router.replace('/staff');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: c.tint, alignItems: 'center', justifyContent: 'center' }}>
        <Icon name="briefcase-outline" size={26} />
      </View>
      <Text variant="title">Sign in to the dashboard</Text>
      <Text variant="muted">Use your staff username and password from the website dashboard. You stay signed in on this phone until you sign out.</Text>
      <Field label="Username" value={username} onChangeText={setUsername} autoCapitalize="none" autoCorrect={false}
        autoComplete="username" textContentType="username" />
      <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry autoComplete="password"
        textContentType="password" onSubmitEditing={signIn} returnKeyType="go" />
      <ErrorText>{error}</ErrorText>
      <Button title="Sign in" icon="log-in-outline" size="lg" loading={busy} disabled={!username || !password} onPress={signIn} />
    </Screen>
  );
}
