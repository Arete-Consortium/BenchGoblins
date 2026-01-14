# Apple App Store Setup Guide

This guide walks you through publishing GameSpace to the Apple App Store with in-app purchases.

## Prerequisites

1. **Apple Developer Account** ($99/year) - https://developer.apple.com
2. **Expo Account** (free) - https://expo.dev
3. **RevenueCat Account** (free tier available) - https://revenuecat.com

## Step 1: Apple Developer Setup

### Create App ID
1. Go to [Apple Developer Portal](https://developer.apple.com/account)
2. Navigate to Certificates, Identifiers & Profiles > Identifiers
3. Click + to create a new App ID
4. Select "App IDs" and continue
5. Enter:
   - Description: GameSpace
   - Bundle ID: `com.gamespace.app` (Explicit)
6. Enable capabilities:
   - In-App Purchase
   - Push Notifications (optional, for future alerts)
7. Click Continue and Register

### Create In-App Purchases in App Store Connect
1. Go to [App Store Connect](https://appstoreconnect.apple.com)
2. Create a new app with your App ID
3. Go to Features > In-App Purchases
4. Create the following subscriptions:

| Reference Name | Product ID | Type | Price |
|---------------|------------|------|-------|
| GameSpace Pro Weekly | `gamespace_pro_weekly` | Auto-Renewable | $2.99/week |
| GameSpace Pro Monthly | `gamespace_pro_monthly` | Auto-Renewable | $7.99/month |
| GameSpace Pro Annual | `gamespace_pro_annual` | Auto-Renewable | $49.99/year |

5. Create a Subscription Group called "GameSpace Pro"
6. Add all subscriptions to this group
7. Set up pricing for each subscription
8. Add subscription descriptions and metadata

## Step 2: RevenueCat Setup

### Create Project
1. Sign up at [RevenueCat Dashboard](https://app.revenuecat.com)
2. Create a new project called "GameSpace"
3. Add iOS platform
4. Configure App Store Connect API:
   - Go to App Store Connect > Users and Access > Keys
   - Create a new API key with "App Manager" access
   - Download the key and note the Key ID and Issuer ID
   - Upload to RevenueCat

### Configure Products
1. In RevenueCat, go to Products
2. Click "Import Products" to import from App Store Connect
3. Create an Entitlement called "pro"
4. Create an Offering called "default"
5. Add packages:
   - `$rc_weekly` → gamespace_pro_weekly
   - `$rc_monthly` → gamespace_pro_monthly
   - `$rc_annual` → gamespace_pro_annual

### Get API Keys
1. Go to Project Settings > API Keys
2. Copy the iOS public API key
3. Update `app.json`:
```json
"extra": {
  "revenueCatApiKey": {
    "ios": "YOUR_ACTUAL_IOS_API_KEY"
  }
}
```

## Step 3: Expo/EAS Setup

### Install EAS CLI
```bash
npm install -g eas-cli
eas login
```

### Configure Project
1. Update `eas.json` with your Apple credentials:
```json
{
  "submit": {
    "production": {
      "ios": {
        "appleId": "your@email.com",
        "ascAppId": "YOUR_APP_STORE_CONNECT_APP_ID",
        "appleTeamId": "YOUR_TEAM_ID"
      }
    }
  }
}
```

2. Link to Expo:
```bash
eas init
```

### Build for iOS
```bash
# Development build (for testing)
eas build --platform ios --profile development

# Production build (for App Store)
eas build --platform ios --profile production
```

### Submit to App Store
```bash
eas submit --platform ios --profile production
```

## Step 4: App Store Connect Submission

### Required Assets
- **App Icon**: 1024x1024 PNG (no alpha)
- **Screenshots**:
  - iPhone 6.9" (1320x2868)
  - iPhone 6.7" (1290x2796)
  - iPhone 6.5" (1284x2778)
  - iPad Pro 12.9" (2048x2732)
- **App Preview Videos** (optional)

### App Information
- **Name**: GameSpace
- **Subtitle**: Fantasy Sports AI Assistant
- **Category**: Sports
- **Description**:
```
GameSpace is your AI-powered fantasy sports decision engine. Get instant analysis for start/sit decisions, trade evaluations, and waiver wire pickups.

Features:
- AI-powered player analysis using Claude
- Start/Sit recommendations with confidence scores
- Risk mode selection (Floor, Median, Ceiling)
- Support for NBA, NFL, MLB, and NHL

Free Features:
- 5 queries per day
- NBA coverage

Pro Features:
- Unlimited queries
- All sports (NBA, NFL, MLB, NHL)
- Advanced AI insights
- Trade analysis
- Waiver alerts
```

### Privacy Information
- **Privacy Policy URL**: https://gamespace.app/privacy
- **Data Collection**: User ID, Usage Data
- **Data Linked to User**: Purchases
- **Data Used for Tracking**: None

### Review Notes
```
Test Account: (provide if needed)
Notes: This app uses RevenueCat for subscription management.
All subscriptions are configured in App Store Connect.
```

## Step 5: Testing

### TestFlight
1. Build with EAS: `eas build --platform ios --profile production`
2. Submit to App Store Connect: `eas submit --platform ios`
3. In App Store Connect, go to TestFlight
4. Add internal testers
5. Test all subscription flows

### Sandbox Testing
1. Create sandbox test accounts in App Store Connect
2. Sign out of App Store on device
3. Sign in with sandbox account
4. Test purchases (no real charges)

## Environment Variables

Create a `.env` file (gitignored):
```
EXPO_PUBLIC_API_URL=https://api.gamespace.app
```

## Checklist Before Submission

- [ ] App icon uploaded (1024x1024)
- [ ] Screenshots for all required sizes
- [ ] Privacy policy hosted and URL added
- [ ] Terms of service hosted and URL added
- [ ] In-app purchases configured and approved
- [ ] RevenueCat API key configured
- [ ] App tested on physical device
- [ ] Subscription flow tested in sandbox
- [ ] App metadata complete
- [ ] Age rating completed
- [ ] Export compliance answered
- [ ] Content rights answered

## Common Issues

### "Your binary is not optimized for iPhone"
Ensure `expo-build-properties` has correct iOS deployment target.

### "Missing required icon"
Check that `assets/icon.png` is 1024x1024 with no transparency.

### "Subscription not found"
Ensure products are "Ready to Submit" in App Store Connect and imported to RevenueCat.

### "Purchase failed"
Check RevenueCat dashboard for error logs. Ensure API key is correct.

## Support

- [Expo Documentation](https://docs.expo.dev)
- [RevenueCat Documentation](https://docs.revenuecat.com)
- [App Store Connect Help](https://developer.apple.com/help/app-store-connect/)
