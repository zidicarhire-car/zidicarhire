/**
 * ZIDICARHIRE brand: the same colours as the website (static/css/theme.css). Indigo is the brand, plate yellow
 * with black is the number-plate signature (prices, booking numbers), green only for M-Pesa and success.
 */
import { useColorScheme } from 'react-native';

const light = {
  brand: '#1C2340',
  onBrand: '#FFFFFF',
  onBrandMuted: '#C9CEE4',
  plate: '#F6C21C',
  plateInk: '#000000',
  bg: '#F3F5F7',
  surface: '#FFFFFF',
  surface2: '#F6F7F9',
  text: '#1C2340',
  muted: '#5A6380',
  border: '#D9DEE6',
  controlBorder: '#7D86A0',
  primary: '#1C2340',
  onPrimary: '#FFFFFF',
  mpesa: '#1F7A2C',
  onMpesa: '#FFFFFF',
  danger: '#B3261E',
  dangerBg: '#FCEBEA',
  successText: '#1B6B27',
  successBg: '#E3F3E6',
  warnText: '#7A4F00',
  warnBg: '#FFF4D6',
  infoText: '#2A3C9E',
  infoBg: '#E3E9FF',
  neutralText: '#1C2340',
  neutralBg: '#E4E8EE',
  tint: '#E4E7F2',
};

export type Palette = typeof light;

const dark: Palette = {
  ...light,
  bg: '#12162B',
  surface: '#1B2140',
  surface2: '#232A4D',
  text: '#E8EBF5',
  muted: '#A3ABC6',
  border: '#2F3860',
  controlBorder: '#6E78A0',
  primary: '#E8EBF5',
  onPrimary: '#1C2340',
  danger: '#FF8A80',
  dangerBg: '#3A1C22',
  successText: '#7FD48A',
  successBg: '#173323',
  warnText: '#F6C21C',
  warnBg: '#3A3016',
  infoText: '#C8D2FF',
  infoBg: '#26306A',
  neutralText: '#E8EBF5',
  neutralBg: '#2F3860',
  tint: '#232A4D',
};

export function useColors(): Palette {
  return useColorScheme() === 'dark' ? dark : light;
}

export const fonts = {
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semibold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
  plate: 'ArchivoNarrow_700Bold',
};

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };
export const radius = { sm: 6, md: 10, lg: 16, pill: 999 };
