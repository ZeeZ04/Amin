// RevenueCat → Supabase: keep public.entitlements in step with purchases.
// RevenueCat is configured with appUserID = the Supabase user id, so
// event.app_user_id is a uuid in auth.users. The shared secret is set in the
// RevenueCat dashboard as the webhook's Authorization header.
import { createClient } from "jsr:@supabase/supabase-js@2";

const PRO_ENTITLEMENT = "pro";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Events after which the person has Pro until expiration_at_ms.
const GRANTS = new Set([
  "INITIAL_PURCHASE", "RENEWAL", "PRODUCT_CHANGE", "UNCANCELLATION",
  "NON_RENEWING_PURCHASE", "SUBSCRIPTION_EXTENDED", "TEMPORARY_ENTITLEMENT_GRANT",
]);
// CANCELLATION and BILLING_ISSUE keep access until expiry, so they only refresh the date.
const KEEPS = new Set(["CANCELLATION", "BILLING_ISSUE", "SUBSCRIPTION_PAUSED"]);

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("method not allowed", { status: 405 });
  const secret = Deno.env.get("REVENUECAT_WEBHOOK_SECRET");
  if (!secret || req.headers.get("Authorization") !== `Bearer ${secret}`) {
    return new Response("unauthorised", { status: 401 });
  }
  const { event } = await req.json().catch(() => ({ event: null }));
  if (!event?.type) return new Response("bad request", { status: 400 });

  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const expires = event.expiration_at_ms ? new Date(event.expiration_at_ms).toISOString() : null;

  const set = async (userId: string, plan: "free" | "pro") => {
    if (!UUID.test(userId)) return; // anonymous RevenueCat ids are not accounts
    const { error } = await db.from("entitlements").upsert({
      user_id: userId, plan,
      product_id: event.product_id ?? null, store: event.store ?? null,
      expires_at: plan === "pro" ? expires : null, updated_at: new Date().toISOString(),
    });
    if (error) throw error;
  };

  const grantsPro = (event.entitlement_ids ?? [PRO_ENTITLEMENT]).includes(PRO_ENTITLEMENT);
  try {
    if (event.type === "TRANSFER") {
      for (const id of event.transferred_from ?? []) await set(id, "free");
      for (const id of event.transferred_to ?? []) await set(id, "pro");
    } else if (GRANTS.has(event.type) || KEEPS.has(event.type)) {
      if (grantsPro) await set(event.app_user_id, "pro");
    } else if (event.type === "EXPIRATION") {
      await set(event.app_user_id, "free");
    }
  } catch (e) {
    console.error("entitlement update failed", e);
    return new Response("retry", { status: 500 }); // RevenueCat retries on 5xx
  }
  return Response.json({ ok: true });
});
