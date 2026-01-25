import * as Haptics from 'expo-haptics';
import { Platform } from 'react-native';

/**
 * Haptic feedback utilities for GameSpace
 *
 * Uses expo-haptics for iOS and Android.
 * Web platform is a no-op (haptics not supported).
 */

const isHapticsSupported = Platform.OS === 'ios' || Platform.OS === 'android';

/**
 * Light tap - for selections, toggles
 */
export function hapticSelection() {
  if (isHapticsSupported) {
    Haptics.selectionAsync();
  }
}

/**
 * Success feedback - for completed actions, received decisions
 */
export function hapticSuccess() {
  if (isHapticsSupported) {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  }
}

/**
 * Error feedback - for failed actions
 */
export function hapticError() {
  if (isHapticsSupported) {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
  }
}

/**
 * Warning feedback - for destructive actions (delete, clear)
 */
export function hapticWarning() {
  if (isHapticsSupported) {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  }
}

/**
 * Light impact - for button presses
 */
export function hapticLight() {
  if (isHapticsSupported) {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  }
}

/**
 * Medium impact - for important actions
 */
export function hapticMedium() {
  if (isHapticsSupported) {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
  }
}
