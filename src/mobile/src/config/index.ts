/**
 * Application configuration for BenchGoblins mobile app.
 */

export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

export const CONFIG = {
  API_BASE_URL,
  REQUEST_TIMEOUT: 30000,
  SESSION_REFRESH_BUFFER_DAYS: 7, // Refresh session if expiring within this many days
} as const;

export default CONFIG;
