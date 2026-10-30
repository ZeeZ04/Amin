// In-app account deletion (App Store Review Guideline 5.1.1(v)).
// The caller's own JWT identifies the account; the service role deletes it,
// and the foreign keys cascade to profiles and entitlements. Nothing else
// about the person is stored in the cloud. An active App Store subscription
// is cancelled by the person in their Apple ID settings; the app links there.
import { createClient } from "jsr:@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, content-type, apikey, x-client-info",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: cors });
  if (req.method !== "POST") return new Response("method not allowed", { status: 405, headers: cors });
  const url = Deno.env.get("SUPABASE_URL")!;
  const asCaller = createClient(url, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: req.headers.get("Authorization") ?? "" } },
  });
  const { data: { user }, error } = await asCaller.auth.getUser();
  if (error || !user) return new Response("unauthorised", { status: 401, headers: cors });

  const admin = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { error: delError } = await admin.auth.admin.deleteUser(user.id);
  if (delError) return new Response("could not delete", { status: 500, headers: cors });
  return Response.json({ deleted: true }, { headers: cors });
});
