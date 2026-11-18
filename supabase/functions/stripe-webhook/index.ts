// Stripe webhook for The Wall Street Edge.
// Verifies the Stripe signature, then records each member's plan in public.subscriptions.
// Needs secret STRIPE_WEBHOOK_SECRET. SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are provided by Supabase.
// Tier: Elite product / prices / payment links => "elite"; any other paid subscription => "pro".
import { createClient } from "npm:@supabase/supabase-js@2";

const ELITE_PRODUCT = "prod_VeGqJorgk5XObo";
const ELITE_PRICES = new Set(["price_1UcyIZBG3VyDk986HZ07AKiN", "price_1UcyIaBG3VyDk986xrrTq9zD"]);
const ELITE_LINKS = new Set(["plink_1UcyIlBG3VyDk986ViJtieug", "plink_1UcyImBG3VyDk986YBozyycJ"]);

function serviceKey(): string {
  const legacy = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (legacy) return legacy;
  const single = Deno.env.get("SUPABASE_SECRET_KEY");
  if (single) return single;
  try {
    const keys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}");
    return keys.default ?? Object.values(keys)[0] as string;
  } catch { return ""; }
}

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  serviceKey(),
  { auth: { persistSession: false } },
);

const enc = new TextEncoder();

async function verify(payload: string, header: string | null, secret: string): Promise<boolean> {
  if (!header) return false;
  const parts = Object.fromEntries(
    header.split(",").map((p) => p.split("=") as [string, string]).filter((p) => p.length === 2 && p[0] === "t"),
  );
  const t = parts["t"];
  const sigs = header.split(",").filter((p) => p.startsWith("v1=")).map((p) => p.slice(3));
  if (!t || sigs.length === 0) return false;
  if (Math.abs(Date.now() / 1000 - Number(t)) > 300) return false;
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(`${t}.${payload}`)));
  const hex = Array.from(mac).map((b) => b.toString(16).padStart(2, "0")).join("");
  return sigs.some((s) => {
    if (s.length !== hex.length) return false;
    let diff = 0;
    for (let i = 0; i < s.length; i++) diff |= s.charCodeAt(i) ^ hex.charCodeAt(i);
    return diff === 0;
  });
}

const PAID = new Set(["active", "trialing", "past_due"]);

function isElitePrice(price: any): boolean {
  if (!price) return false;
  const product = typeof price.product === "string" ? price.product : price.product?.id;
  return ELITE_PRICES.has(price.id) || product === ELITE_PRODUCT;
}

function paidTierFrom(sub: any): "pro" | "elite" {
  const items = sub?.items?.data ?? [];
  return items.some((it: any) => isElitePrice(it?.price ?? it?.plan)) ? "elite" : "pro";
}

function planFrom(sub: any): string | null {
  const interval = sub?.items?.data?.[0]?.price?.recurring?.interval;
  return interval === "year" ? "annual" : interval === "month" ? "monthly" : null;
}

function periodEnd(sub: any): string | null {
  const ts = sub?.current_period_end ?? sub?.items?.data?.[0]?.current_period_end;
  return ts ? new Date(ts * 1000).toISOString() : null;
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("ok");
  const secret = Deno.env.get("STRIPE_WEBHOOK_SECRET");
  if (!secret) return new Response("webhook secret not configured", { status: 500 });
  const body = await req.text();
  if (!(await verify(body, req.headers.get("stripe-signature"), secret))) {
    return new Response("bad signature", { status: 400 });
  }
  const event = JSON.parse(body);
  const obj = event.data?.object ?? {};

  try {
    if (event.type === "checkout.session.completed") {
      const userId = obj.client_reference_id;
      if (!userId) return new Response("no client_reference_id, ignored");
      const trialing = obj.payment_status === "no_payment_required";
      const tier = ELITE_LINKS.has(obj.payment_link) || obj.metadata?.tier === "elite" ? "elite" : "pro";
      const { error } = await supabase.from("subscriptions").upsert({
        user_id: userId,
        tier,
        status: trialing ? "trialing" : "active",
        stripe_customer_id: obj.customer ?? null,
        stripe_subscription_id: obj.subscription ?? null,
        updated_at: new Date().toISOString(),
      });
      if (error) throw error;
    } else if (event.type.startsWith("customer.subscription.")) {
      const status = event.type === "customer.subscription.deleted" ? "canceled" : obj.status;
      const row = {
        status,
        tier: PAID.has(status) ? paidTierFrom(obj) : "free",
        plan: planFrom(obj),
        current_period_end: periodEnd(obj),
        stripe_subscription_id: obj.id,
        updated_at: new Date().toISOString(),
      };
      const { data, error } = await supabase.from("subscriptions").update(row)
        .eq("stripe_customer_id", obj.customer).select("user_id");
      if (error) throw error;
      if (!data || data.length === 0) {
        // checkout.session.completed has not landed yet; ask Stripe to retry shortly
        if (event.type === "customer.subscription.created") return new Response("ok, pending checkout");
        return new Response("customer not linked yet", { status: 409 });
      }
    }
    return new Response(JSON.stringify({ received: true }), { headers: { "Content-Type": "application/json" } });
  } catch (e) {
    console.error(e);
    return new Response("handler error", { status: 500 });
  }
});
