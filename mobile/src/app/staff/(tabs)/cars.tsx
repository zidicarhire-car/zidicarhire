import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { useState } from 'react';
import { ActionSheetIOS, Alert, FlatList, Platform, RefreshControl, Switch, View } from 'react-native';

import { Button, Card, EmptyState, ErrorText, Icon, Loading, Plate, Row, Text } from '@/components/ui';
import { ApiError, get, request } from '@/lib/api';
import { kes } from '@/lib/format';
import type { Car } from '@/lib/types';
import { useStaff } from '@/state/staff';
import { radius, space, useColors } from '@/theme';

type StaffCar = Car & { is_active: boolean; units: number };

export default function StaffCars() {
  const c = useColors();
  const staff = useStaff();
  const qc = useQueryClient();
  const [uploading, setUploading] = useState<number | null>(null);
  const { data, isLoading, error, refetch, isRefetching } = useQuery({
    queryKey: ['staff', 'cars'],
    queryFn: () => staff.call((token) => get<{ cars: StaffCar[] }>('staff/cars/', { token }).then((r) => r.cars)),
  });

  async function toggle(car: StaffCar) {
    qc.setQueryData<StaffCar[]>(['staff', 'cars'], (old) => old?.map((x) => (x.id === car.id ? { ...x, is_active: !x.is_active } : x)));
    try {
      await staff.call((token) => request(`staff/cars/${car.id}/toggle/`, { token, method: 'POST', body: {} }));
    } catch (err) {
      qc.setQueryData<StaffCar[]>(['staff', 'cars'], (old) => old?.map((x) => (x.id === car.id ? { ...x, is_active: car.is_active } : x)));
      Alert.alert("Couldn't change it", (err as Error).message);
    }
  }

  async function addPhoto(car: StaffCar, fromCamera: boolean) {
    const permission = fromCamera ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('Permission needed', fromCamera ? 'Allow camera access in your phone settings to take car photos.' : 'Allow photo access in your phone settings.');
      return;
    }
    const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.85 };
    const picked = fromCamera ? await ImagePicker.launchCameraAsync(options) : await ImagePicker.launchImageLibraryAsync(options);
    if (picked.canceled || !picked.assets.length) return;
    const asset = picked.assets[0];
    const form = new FormData();
    // React Native's FormData takes a { uri, name, type } file object.
    form.append('image', { uri: asset.uri, name: asset.fileName ?? 'car.jpg', type: asset.mimeType ?? 'image/jpeg' } as unknown as Blob);
    setUploading(car.id);
    try {
      await staff.call((token) => request(`staff/cars/${car.id}/photos/`, { token, method: 'POST', form }));
      qc.invalidateQueries({ queryKey: ['staff', 'cars'] });
      Alert.alert('Photo added', `The photo is now on ${car.name}. Set the cover photo on the website dashboard if needed.`);
    } catch (err) {
      Alert.alert('Upload failed', err instanceof ApiError ? err.message : 'Check your connection and try again.');
    } finally {
      setUploading(null);
    }
  }

  function choosePhoto(car: StaffCar) {
    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions({ options: ['Take a photo', 'Choose from photos', 'Cancel'], cancelButtonIndex: 2 },
        (i) => { if (i < 2) addPhoto(car, i === 0); });
    } else {
      Alert.alert(`Add a photo of the ${car.name}`, undefined, [
        { text: 'Take a photo', onPress: () => addPhoto(car, true) },
        { text: 'Choose from photos', onPress: () => addPhoto(car, false) },
        { text: 'Cancel', style: 'cancel' },
      ]);
    }
  }

  if (isLoading) return <Loading />;
  return (
    <FlatList
      style={{ backgroundColor: c.bg }}
      data={data ?? []}
      keyExtractor={(car) => String(car.id)}
      contentContainerStyle={{ padding: space.lg, gap: space.md }}
      refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => { refetch(); }} />}
      ListHeaderComponent={error ? <ErrorText>{(error as Error).message}</ErrorText> : undefined}
      ListEmptyComponent={<EmptyState icon="car-outline" title="No cars yet" text="Add cars on the website dashboard, then manage them here." />}
      renderItem={({ item }) => (
        <Card style={{ padding: 0, overflow: 'hidden', gap: 0, opacity: item.is_active ? 1 : 0.75 }}>
          <Row gap={space.md} style={{ padding: space.md, alignItems: 'flex-start' }}>
            <View style={{ width: 96, height: 60, borderRadius: radius.sm, backgroundColor: c.surface2, overflow: 'hidden', alignItems: 'center', justifyContent: 'center' }}>
              {item.photo ? <Image source={item.photo} style={{ width: 96, height: 60 }} contentFit="cover" /> : <Icon name="camera-outline" color={c.muted} />}
            </View>
            <View style={{ flex: 1, gap: 4 }}>
              <Text variant="subheading">{item.name}</Text>
              <Text variant="muted">{item.location.name} · {item.category_label}, {item.seats} seats</Text>
              <Plate size="sm">{kes(item.price_per_day)}/day</Plate>
            </View>
          </Row>
          <Row style={{ borderTopWidth: 1, borderTopColor: c.border, paddingHorizontal: space.md, paddingVertical: space.sm, justifyContent: 'space-between' }}>
            <Row gap={space.sm}>
              <Switch value={item.is_active} onValueChange={() => toggle(item)} accessibilityLabel={`Show ${item.name} on the website`} />
              <Text variant="label">{item.is_active ? 'Shown on website' : 'Hidden'}</Text>
            </Row>
            <Button title="Add photo" icon="camera-outline" kind="ghost" size="sm" loading={uploading === item.id} onPress={() => choosePhoto(item)} />
          </Row>
        </Card>
      )}
    />
  );
}
