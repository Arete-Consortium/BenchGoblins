# App Store Setup Guide

## Prerequisites

- Apple Developer Account ($99/year)
- Expo account (free)
- RevenueCat account (free tier available)

---

## 1. EAS Setup

```bash
cd src/mobile

# Login to Expo
npx eas-cli login

# Initialize EAS project (links to Expo)
npx eas-cli init

# This will update app.json with your project ID
```

After init, your `app.json` will have:
```json
"extra": {
  "eas": {
    "projectId": "your-actual-project-id"
  }
}
```

---

## 2. RevenueCat Setup

### Create App in RevenueCat Dashboard

1. Go to https://app.revenuecat.com
2. Create new project: "GameSpace"
3. Add iOS app:
   - Bundle ID: `com.gamespace.app`
   - App Store Connect App-Specific Shared Secret (get from App Store Connect)

### Create Products

In RevenueCat Dashboard → Products:

| Identifier | Type | Price |
|------------|------|-------|
| `gamespace_pro_weekly` | Auto-renewable | $4.99/week |
| `gamespace_pro_monthly` | Auto-renewable | $9.99/month |
| `gamespace_pro_annual` | Auto-renewable | $49.99/year |

### Create Entitlement

- Entitlement ID: `pro`
- Attach all 3 products to this entitlement

### Create Offering

- Offering ID: `default`
- Add all 3 packages:
  - `$rc_weekly` → gamespace_pro_weekly
  - `$rc_monthly` → gamespace_pro_monthly
  - `$rc_annual` → gamespace_pro_annual

### Get API Keys

Copy your iOS API key and update `app.json`:
```json
"revenueCatApiKey": {
  "ios": "appl_xxxxxxxxxxxxx",
  "android": "goog_xxxxxxxxxxxxx"
}
```

---

## 3. App Store Connect Setup

### Create App

1. Go to https://appstoreconnect.apple.com
2. My Apps → + → New App
3. Fill in:
   - Platform: iOS
   - Name: GameSpace
   - Primary Language: English (US)
   - Bundle ID: com.gamespace.app
   - SKU: gamespace-ios-001

### Create In-App Purchases

Go to your app → Features → In-App Purchases → +

For each product:

**Weekly ($4.99)**
- Reference Name: GameSpace Pro Weekly
- Product ID: `gamespace_pro_weekly`
- Type: Auto-Renewable Subscription
- Subscription Group: GameSpace Pro
- Price: $4.99
- Localization: Add title/description

**Monthly ($9.99)**
- Reference Name: GameSpace Pro Monthly
- Product ID: `gamespace_pro_monthly`
- Type: Auto-Renewable Subscription
- Subscription Group: GameSpace Pro
- Price: $9.99

**Annual ($49.99)**
- Reference Name: GameSpace Pro Annual
- Product ID: `gamespace_pro_annual`
- Type: Auto-Renewable Subscription
- Subscription Group: GameSpace Pro
- Price: $49.99

### Get Shared Secret

1. App Store Connect → Your App → General → App Information
2. Scroll to "App-Specific Shared Secret"
3. Generate if needed
4. Copy to RevenueCat iOS app settings

---

## 4. Build & Submit

### Development Build (for testing)

```bash
# Create development build
npx eas-cli build --profile development --platform ios
```

### Production Build

```bash
# Create production build
npx eas-cli build --profile production --platform ios

# Submit to App Store
npx eas-cli submit --platform ios
```

---

## 5. Testing

### Sandbox Testing

1. Create sandbox tester in App Store Connect → Users and Access → Sandbox Testers
2. On device, sign out of App Store
3. When prompted during purchase, sign in with sandbox account
4. Purchases are free and auto-renew quickly (weekly = 3 min)

### TestFlight

1. Upload build via EAS submit
2. Add internal testers in App Store Connect → TestFlight
3. Testers receive invite to install

---

## Checklist

- [ ] EAS project initialized
- [ ] RevenueCat project created
- [ ] RevenueCat iOS app added with shared secret
- [ ] Products created in RevenueCat
- [ ] Entitlement "pro" created
- [ ] Offering "default" created
- [ ] App Store Connect app created
- [ ] In-app purchases created in App Store Connect
- [ ] API keys added to app.json
- [ ] Development build tested on device
- [ ] Sandbox purchases working
- [ ] Production build submitted

---

## App Store Review Preparation

### Required Before Submission

1. **Screenshots** — 6.7" (iPhone 15 Pro Max) and 6.5" (iPhone 14 Plus) at minimum
   - Dashboard screen
   - Decision comparison screen
   - Roster view
   - Settings/subscription screen
2. **App Description** — 4000 chars max, focus on fantasy sports decision-making
3. **Keywords** — 100 chars: "fantasy,sports,nba,nfl,mlb,nhl,start,sit,roster,decision"
4. **Privacy URL** — `https://aretedriver.github.io/GameSpace/legal/privacy-policy.html`
5. **Support URL** — `https://github.com/AreteDriver/GameSpace/issues`
6. **App Category** — Sports
7. **Age Rating** — 4+ (no objectionable content)

### Common Rejection Reasons to Avoid

- **Guideline 2.1** — App must be complete (no placeholder text, broken links, or lorem ipsum)
- **Guideline 3.1.1** — In-app purchases must use Apple's payment system (RevenueCat handles this)
- **Guideline 5.1.1** — Must have valid privacy policy URL
- **Guideline 4.0** — App must provide enough value beyond a website

### Submission Commands

```bash
cd src/mobile

# Build for production
npx eas-cli build --profile production --platform ios

# Submit to App Store Connect
npx eas-cli submit --platform ios

# Or build + submit in one step
npx eas-cli build --profile production --platform ios --auto-submit
```

---

## Environment Variables

For CI/CD, set these in your build environment:

```
EXPO_TOKEN=your_expo_token
```

Get token from: https://expo.dev/accounts/[your-account]/settings/access-tokens
