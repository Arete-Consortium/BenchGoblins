/**
 * Notification Store
 *
 * Manages push notification state, preferences, and device token.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import {
  registerForPushNotifications,
  setupNotificationChannel,
  areNotificationsEnabled,
  addNotificationResponseListener,
  addNotificationReceivedListener,
  getLastNotificationResponse,
} from '../utils/notifications';
import { registerPushToken, unregisterPushToken } from '../services/api';
import type { Subscription } from 'expo-notifications';

export interface NotificationPreferences {
  injuryAlerts: boolean;
  lineupReminders: boolean;
  decisionUpdates: boolean;
  trendingPlayers: boolean;
}

interface NotificationState {
  // Token state
  pushToken: string | null;
  isRegistered: boolean;
  isEnabled: boolean;

  // Preferences
  preferences: NotificationPreferences;

  // Actions
  initialize: () => Promise<void>;
  enableNotifications: () => Promise<boolean>;
  disableNotifications: () => Promise<void>;
  updatePreference: (key: keyof NotificationPreferences, value: boolean) => void;
  setAllPreferences: (prefs: NotificationPreferences) => void;
}

const DEFAULT_PREFERENCES: NotificationPreferences = {
  injuryAlerts: true,
  lineupReminders: true,
  decisionUpdates: true,
  trendingPlayers: false,
};

export const useNotificationStore = create<NotificationState>()(
  persist(
    (set, get) => ({
      pushToken: null,
      isRegistered: false,
      isEnabled: false,

      preferences: DEFAULT_PREFERENCES,

      initialize: async () => {
        // Setup Android notification channels
        await setupNotificationChannel();

        // Check if notifications are currently enabled
        const enabled = await areNotificationsEnabled();
        set({ isEnabled: enabled });

        // If we have a stored token and permissions, we're registered
        const { pushToken } = get();
        if (pushToken && enabled) {
          set({ isRegistered: true });
        }

        // Handle notification that opened the app
        const lastResponse = await getLastNotificationResponse();
        if (lastResponse) {
          handleNotificationNavigation(lastResponse.notification.request.content.data);
        }
      },

      enableNotifications: async () => {
        const token = await registerForPushNotifications();

        if (token) {
          // Register token with backend
          try {
            await registerPushToken(token);
          } catch (error) {
            console.error('Failed to register push token with backend:', error);
          }

          set({
            pushToken: token,
            isRegistered: true,
            isEnabled: true,
          });

          return true;
        }

        return false;
      },

      disableNotifications: async () => {
        const { pushToken } = get();

        if (pushToken) {
          // Unregister from backend
          try {
            await unregisterPushToken(pushToken);
          } catch (error) {
            console.error('Failed to unregister push token:', error);
          }
        }

        set({
          pushToken: null,
          isRegistered: false,
          isEnabled: false,
        });
      },

      updatePreference: (key, value) => {
        set((state) => ({
          preferences: {
            ...state.preferences,
            [key]: value,
          },
        }));
      },

      setAllPreferences: (prefs) => {
        set({ preferences: prefs });
      },
    }),
    {
      name: 'gamespace-notifications',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({
        pushToken: state.pushToken,
        isRegistered: state.isRegistered,
        preferences: state.preferences,
      }),
    },
  ),
);

// Notification navigation handler
function handleNotificationNavigation(data: Record<string, unknown> | undefined) {
  if (!data) return;

  const type = data.type as string | undefined;
  const playerId = data.playerId as string | undefined;

  // Handle different notification types
  switch (type) {
    case 'injury':
      // Navigate to player details or decision screen
      console.log('Injury notification for player:', playerId);
      break;
    case 'lineup_reminder':
      // Navigate to roster screen
      console.log('Lineup reminder notification');
      break;
    case 'decision_update':
      // Navigate to decision history
      console.log('Decision update notification');
      break;
    default:
      console.log('Unknown notification type:', type);
  }
}

// Setup notification listeners (call this in App.tsx)
let notificationListener: Subscription | null = null;
let responseListener: Subscription | null = null;

export function setupNotificationListeners() {
  // Listener for notifications received while app is in foreground
  notificationListener = addNotificationReceivedListener((notification) => {
    console.log('Notification received:', notification.request.content);
  });

  // Listener for when user taps on notification
  responseListener = addNotificationResponseListener((response) => {
    const data = response.notification.request.content.data;
    handleNotificationNavigation(data);
  });
}

export function removeNotificationListeners() {
  if (notificationListener) {
    notificationListener.remove();
    notificationListener = null;
  }
  if (responseListener) {
    responseListener.remove();
    responseListener = null;
  }
}
