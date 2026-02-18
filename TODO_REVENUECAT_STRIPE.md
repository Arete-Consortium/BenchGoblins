# RevenueCat + Stripe Setup TODO

## Status: Code is deployed and ready. Just needs dashboard configuration.

### 1. Create Stripe Products/Prices
- [ ] Go to https://dashboard.stripe.com → Products → + Add product
- [ ] Create "BenchGoblins Pro" with 4 recurring prices:
  - Weekly: $2.99/week
  - Monthly: $9.99/month
  - Pro Seasonal: $24.99/3 months
  - League Seasonal: $24.99/3 months
- [ ] Copy each `price_` ID after creation

### 2. Link Stripe Prices in RevenueCat (Stripe App)
- [ ] Go to https://app.revenuecat.com → Products
- [ ] For `benchgoblins_pro_weekly` → edit Bench Goblins (Stripe) entry → paste weekly `price_` ID
- [ ] For `benchgoblins_pro_monthly` → paste monthly `price_` ID
- [ ] For `benchgoblins_pro_seasonal` → paste seasonal `price_` ID
- [ ] For `benchgoblins_league_seasonal` → paste league seasonal `price_` ID
- [ ] Verify "Store Status" changes from "Not found" to active

### 3. Link Stripe Prices in RevenueCat (RC Billing App)
- [ ] For each of the 4 products above, click "+ Add App"
- [ ] Select the RC Billing app
- [ ] Paste the same Stripe `price_` ID
- [ ] This is what makes packages appear in the Web SDK

### 4. Verify
- [ ] Test: `curl -s -H "Authorization: Bearer rcb_sdBACaGNVHJFmeycjeZrAYDkqgAR" "https://api.revenuecat.com/v1/subscribers/test_user/offerings"` — packages should no longer be empty
- [ ] Visit https://benchgoblins.com/billing — plans should appear
- [ ] Test "Upgrade to Pro" button opens Stripe checkout

### 5. Optional: Set Offering as Current
- [ ] In RevenueCat → Offerings → verify "Bench Default" is marked as the current offering

## What's Already Done
- ✅ RevenueCat project created with RC Billing app
- ✅ `rcb_` API key set on Vercel (no trailing newline)
- ✅ Web SDK lazy-loaded to prevent SSR crashes
- ✅ Billing page uses direct purchase flow (not managed paywall)
- ✅ Product IDs aligned across web + mobile code
- ✅ Stripe connected to RevenueCat (Arete Sandbox account)
- ✅ `pro` entitlement created
- ✅ Offering "Bench Default" with 4 packages configured
- ✅ All code deployed, 976 tests passing
