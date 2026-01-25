/**
 * Push Notification Utilities
 *
 * Handles push notification permissions, token registration,
 * and notification handling for GameSpace.
 */

import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import Constants from 'expo-constants';

// Configure how notifications appear when app is in foreground
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export interface NotificationPreferences {
  injuryAlerts: boolean;
  lineupReminders: boolean;
  decisionUpdates: boolean;
  trendingPlayers: boolean;
}

const DEFAULT_PREFERENCES: NotificationPreferences = {
  injuryAlerts: true,
  lineupReminders: true,
  decisionUpdates: true,
  trendingPlayers: false,
};

/**
 * Request permission to send push notifications.
 * Returns the Expo push token if granted.
 */
export async function registerForPushNotifications(): Promise<string | null> {
  // Only physical devices can receive push notifications
  if (!Device.isDevice) {
    console.log('Push notifications require a physical device');
    return null;
  }

  // Check current permission status
  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  // Request permission if not already granted
  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== 'granted') {
    console.log('Push notification permission denied');
    return null;
  }

  // Get the Expo push token
  try {
    const projectId = Constants.expoConfig?.extra?.eas?.projectId;

    const token = await Notifications.getExpoPushTokenAsync({
      projectId: projectId,
    });

    return token.data;
  } catch (error) {
    console.error('Failed to get push token:', error);
    return null;
  }
}

/**
 * Configure Android notification channel (required for Android 8+).
 */
export async function setupNotificationChannel(): Promise<void> {
  if (Platform.OS === 'android') {
    // Main notification channel
    await Notifications.setNotificationChannelAsync('default', {
      name: 'GameSpace Alerts',
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#818CF8',
    });

    // Injury alerts channel (high priority)
    await Notifications.setNotificationChannelAsync('injuries', {
      name: 'Injury Alerts',
      description: 'Important player injury updates',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 500, 250, 500],
      lightColor: '#EF4444',
    });

    // Lineup reminders channel
    await Notifications.setNotificationChannelAsync('reminders', {
      name: 'Lineup Reminders',
      description: 'Reminders before lineup locks',
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#22C55E',
    });
  }
}

/**
 * Schedule a local notification (for testing or offline reminders).
 */
export async function scheduleLocalNotification(
  title: string,
  body: string,
  triggerSeconds: number = 5,
  channelId: string = 'default',
): Promise<string> {
  const id = await Notifications.scheduleNotificationAsync({
    content: {
      title,
      body,
      sound: true,
      priority: Notifications.AndroidNotificationPriority.HIGH,
      ...(Platform.OS === 'android' ? { channelId } : {}),
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
      seconds: triggerSeconds,
    },
  });

  return id;
}

/**
 * Cancel a scheduled notification.
 */
export async function cancelNotification(notificationId: string): Promise<void> {
  await Notifications.cancelScheduledNotificationAsync(notificationId);
}

/**
 * Cancel all scheduled notifications.
 */
export async function cancelAllNotifications(): Promise<void> {
  await Notifications.cancelAllScheduledNotificationsAsync();
}

/**
 * Get the current badge count.
 */
export async function getBadgeCount(): Promise<number> {
  return await Notifications.getBadgeCountAsync();
}

/**
 * Set the badge count on the app icon.
 */
export async function setBadgeCount(count: number): Promise<void> {
  await Notifications.setBadgeCountAsync(count);
}

/**
 * Clear the badge count.
 */
export async function clearBadge(): Promise<void> {
  await Notifications.setBadgeCountAsync(0);
}

/**
 * Add notification response listener.
 * Called when user taps on a notification.
 */
export function addNotificationResponseListener(
  handler: (response: Notifications.NotificationResponse) => void,
): Notifications.Subscription {
  return Notifications.addNotificationResponseReceivedListener(handler);
}

/**
 * Add notification received listener.
 * Called when notification is received while app is in foreground.
 */
export function addNotificationReceivedListener(
  handler: (notification: Notifications.Notification) => void,
): Notifications.Subscription {
  return Notifications.addNotificationReceivedListener(handler);
}

/**
 * Check if notifications are enabled.
 */
export async function areNotificationsEnabled(): Promise<boolean> {
  const { status } = await Notifications.getPermissionsAsync();
  return status === 'granted';
}

/**
 * Get the last notification response (if app was opened from notification).
 */
export async function getLastNotificationResponse(): Promise<Notifications.NotificationResponse | null> {
  return await Notifications.getLastNotificationResponseAsync();
}
