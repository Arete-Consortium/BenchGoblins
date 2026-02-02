# Bench Goblins Deployment Checklist

## Status: Code ready, deployment pending

---

## 1. Google Cloud Setup (5 min)
- [ ] Go to: https://console.cloud.google.com/apis/credentials
- [ ] Create OAuth 2.0 Client ID (Web application)
- [ ] App name: `Bench Goblins`
- [ ] Authorized JavaScript origins: `https://benchgoblins.com`
- [ ] Authorized redirect URIs: `https://benchgoblins.com`
- [ ] Copy **Client ID** (save for later)

---

## 2. Stripe Setup (5 min)
- [ ] Go to: https://dashboard.stripe.com/test/apikeys
- [ ] Copy **Secret Key** (sk_test_...)
- [ ] Go to: https://dashboard.stripe.com/test/products/create
- [ ] Create product: `Bench Goblins Pro` - $9.99/month recurring
- [ ] Copy **Price ID** (price_...)
- [ ] Webhook setup (do after Railway deploys):
  - URL: `https://api.benchgoblins.com/billing/webhook`
  - Events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`

---

## 3. Deploy Frontend to Vercel (5 min)
- [ ] Go to: https://vercel.com/new/import?s=https://github.com/AreteDriver/BenchGoblins
- [ ] Root Directory: `src/web`
- [ ] Add Environment Variables:
  ```
  NEXT_PUBLIC_API_URL=https://api.benchgoblins.com
  NEXT_PUBLIC_GOOGLE_CLIENT_ID=<from step 1>
  ```
- [ ] Deploy
- [ ] Add custom domain: `benchgoblins.com`

---

## 4. Deploy Backend to Railway (5 min)
- [ ] Go to: https://railway.app/new/github
- [ ] Import: `AreteDriver/BenchGoblins`
- [ ] Root Directory: `src/api`
- [ ] Add Environment Variables:
  ```
  ANTHROPIC_API_KEY=<your key>
  GOOGLE_CLIENT_ID=<from step 1>
  JWT_SECRET_KEY=<run: openssl rand -hex 32>
  STRIPE_SECRET_KEY=<from step 2>
  STRIPE_WEBHOOK_SECRET=<after webhook setup>
  STRIPE_PRO_MONTHLY_PRICE_ID=<from step 2>
  DATABASE_URL=<Railway will provide>
  ```
- [ ] Deploy
- [ ] Note the Railway URL for API

---

## 5. Connect Domain (GoDaddy DNS)
- [ ] Go to: https://dashboard.godaddy.com (DNS settings)
- [ ] Add/Update records:

| Type  | Name | Value                          |
|-------|------|--------------------------------|
| CNAME | @    | cname.vercel-dns.com           |
| CNAME | www  | cname.vercel-dns.com           |
| CNAME | api  | <your-railway-url>.railway.app |

---

## 6. Final Steps
- [ ] Test: https://benchgoblins.com
- [ ] Test Google Sign-In
- [ ] Test a query (should work with Claude)
- [ ] Set up Stripe webhook (now that API is live)
- [ ] Switch Stripe to live keys when ready to charge real money

---

## Quick Reference

**GitHub Repo**: https://github.com/AreteDriver/BenchGoblins
**Domain**: https://benchgoblins.com
**GoDaddy**: https://dashboard.godaddy.com

**Local Dev**:
```bash
# Frontend (port 3001)
cd ~/projects/BenchGoblins/src/web && PORT=3001 npm run dev

# Backend (port 8000)
cd ~/projects/BenchGoblins/src/api && source .venv/bin/activate && uvicorn main:app --reload
```

---

Good luck! 🎮👹
