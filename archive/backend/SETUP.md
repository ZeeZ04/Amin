# Going public: the services and the steps

Decision (2026-10-30): the cloud holds **accounts and subscriptions only**.
Questions, documents, memory and conversations stay on each person's devices.
Model weights download once from Hugging Face. Pro is sold through RevenueCat.

| Service | What it does for Amin | Cost to start |
|---|---|---|
| Supabase | Sign-up, sign-in, password reset, the `profiles` and `entitlements` tables, two edge functions | Free tier |
| RevenueCat | Sells Pro on the App Store and Google Play; tells Supabase via webhook | Free up to $2.5k/month revenue |
| Hugging Face | Hosts the model files the app downloads | Free |
| Vercel | The website: landing, privacy, terms, DMCA, support, account deletion | Free (Hobby) |
| Apple Developer / Google Play | Store accounts | $99/year / $25 once |
| US Copyright Office | DMCA designated agent registration | $6, renew every 3 years |

Claude built the code; the accounts are yours to create, and keys are pasted by
you into the files named below (never committed: they are gitignored).

## 1. Supabase

1. Create a project at supabase.com (region near your users). Note the project ref.
2. Install the CLI and log in: `brew install supabase/tap/supabase`, then `supabase login`.
3. From `backend/`: `supabase link --project-ref <ref>`, then `supabase db push`
   (creates `profiles`, `entitlements`, the sign-up trigger and `is_pro()`).
4. Webhook secret: `openssl rand -hex 32`, then
   `supabase secrets set REVENUECAT_WEBHOOK_SECRET=<that value>`.
5. `supabase functions deploy revenuecat-webhook delete-account`.
6. Dashboard › Authentication › URL configuration: Site URL `https://amin.vercel.app`
   (or your domain); redirect URLs `amin://auth-callback` and
   `https://amin.vercel.app/auth/confirmed`.
7. Dashboard › Authentication › SMTP: before launch, connect a sending service
   (Resend or Postmark). Supabase's built-in email is rate-limited to a few per hour.
8. Optional local test (needs Docker): `supabase start && supabase db reset`.

## 2. App Store Connect and RevenueCat

1. App Store Connect: create the app (bundle id `app.amin.Amin`), and two
   auto-renewable subscriptions in one group: `amin_pro_monthly`, `amin_pro_yearly`.
2. RevenueCat: create a project, add the App Store app with an In-App Purchase key.
   Create the entitlement **`pro`** (the exact id the app and webhook use), attach
   both products, put them in the `default` offering, and design the paywall there
   (the app shows RevenueCat's PaywallView).
3. RevenueCat › Integrations › Webhooks: URL
   `https://<ref>.supabase.co/functions/v1/revenuecat-webhook`, Authorization header
   `Bearer <the secret from 1.4>`.
4. Copy the **public** Apple SDK key (starts `appl_`).

## 3. Hugging Face

1. Create an account and an organisation (for example `amin-ai`).
2. Read `docs/TRAINING.md`: publishing makes the weights public.
3. `uv run hf auth login` with a write token, then
   `uv run python scripts/publish_model.py <org> edge-2-m46 edge-2-q6 edge-2-q8`.

## 4. The app

1. `cp apple/Config/Secrets.example.xcconfig apple/Config/Secrets.xcconfig` and fill in
   the Supabase URL and anon key (Settings › API), the RevenueCat key, and the HF org.
   The anon key and RevenueCat public key are made to ship in apps; the service-role
   key and webhook secret must never go here.
2. In `apple/project.yml` set `DEVELOPMENT_TEAM`, run `xcodegen`, and add the
   In-App Purchase capability.
3. App Store privacy labels: Contact Info › Email (app functionality, linked to the
   user, not used for tracking); Purchases (app functionality). Nothing else is collected.

With the keys empty the app works as before (Amin computer or a chosen model folder),
so development never depends on the services.

## 5. Website (Vercel)

1. Fill `OWNER` in `scripts/build_site.py` (legal name, support email, postal address,
   governing country), then `uv run python scripts/build_site.py`.
2. `cd site && vercel` (log in, link a new project), then `vercel --prod`.
3. Optional: add your own domain in Vercel, and use it in steps 1.6 and the app's links.

## 6. DMCA

Register a designated agent at the US Copyright Office's DMCA Designated Agent
Directory (dmca.copyright.gov) with the same name and address as `site/dmca.html`.

## 7. Before launch

- Have a lawyer read the privacy policy, terms and DMCA policy (`scripts/build_site.py`).
- Sign in with Apple becomes required if you ever add Google or another social sign-in.
- Android: the same Supabase and RevenueCat projects serve the Android app when it exists.
