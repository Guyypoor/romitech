// RomiTech – ביטול עסקה + מסמך זיכוי מפאנל הניהול (רק מנהל מחובר). 22/10/2026
// אם יש חשבונית מהתשלום: Documents/CancelDoc (מבטל את החשבונית ואת חיוב האשראי יחד, ומוציא מסמך זיכוי ללקוח).
// אחרת: Transactions/RefundByTransactionId. דורש סוד CARDCOM_API_PASSWORD (מפתח עם הרשאת ביטול/זיכוי).
const SB = Deno.env.get("SUPABASE_URL")!;
const SR = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ANON = Deno.env.get("SUPABASE_ANON_KEY")!;
const API = Deno.env.get("CARDCOM_API_NAME_ADMIN") || Deno.env.get("CARDCOM_API_NAME")!;
const PASS = Deno.env.get("CARDCOM_API_PASSWORD") || "";
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type", "Access-Control-Allow-Methods": "POST, OPTIONS" };
const j = (o: unknown, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { ...CORS, "Content-Type": "application/json" } });
async function db(path: string, init: RequestInit = {}) {
  const r = await fetch(SB + "/rest/v1/" + path, { ...init, headers: { apikey: SR, Authorization: "Bearer " + SR, "Content-Type": "application/json", Prefer: "return=representation", ...(init.headers || {}) } });
  const t = await r.text(); if (!r.ok) throw new Error("db " + r.status + " " + t.slice(0, 200)); return t ? JSON.parse(t) : null;
}
const cc = (path: string, body: unknown) => fetch("https://secure.cardcom.solutions/api/v11/" + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json());

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  try {
    const tok = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
    const adm = await fetch(SB + "/rest/v1/rpc/rt_is_admin", { method: "POST", headers: { apikey: ANON, Authorization: "Bearer " + tok, "Content-Type": "application/json" }, body: "{}" });
    if (!adm.ok || (await adm.json()) !== true) return j({ error: "not_admin" }, 403);
    if (!PASS) return j({ error: "no_password", desc: "חסר סוד CARDCOM_API_PASSWORD ב-Supabase" }, 412);
    const { id } = await req.json();
    if (!/^RT-\d{6}$/.test(String(id || ""))) return j({ error: "bad_id" }, 400);
    const o = (await db("rt_orders?id=eq." + id + "&select=*"))?.[0];
    if (!o) return j({ error: "not_found" }, 404);
    if (o.pay_status !== "paid") return j({ error: "not_paid", desc: "ההזמנה לא במצב 'שולם'" }, 409);
    const hook = [...(o.log || [])].reverse().find((e: any) => e.ev === "pay_hook" && e.tx);
    const tx = Number(hook?.tx || o.pay_ref);
    const doc = Number(hook?.doc || 0);
    let res: any, how: string;
    if (doc > 0) {
      how = "CancelDoc";
      res = await cc("Documents/CancelDoc", { ApiName: API, ApiPassword: PASS, DocumentNumber: doc, DocumentType: 1, IsCancelEmailSend: false, IsSendSMS: false, IsCreditCardCancelOnly: false });
    } else {
      how = "Refund";
      res = await cc("Transactions/RefundByTransactionId", { ApiName: API, ApiPassword: PASS, TransactionId: tx });
    }
    const ok = res && res.ResponseCode === 0;
    const ev = { at: new Date().toISOString(), ev: "refund", how, code: res?.ResponseCode, desc: res?.Description, tx, doc, new_tx: res?.NewTranzactionId ?? null, new_doc: res?.DocumentNumber ?? res?.NewDocumentNumber ?? null };
    const patch: Record<string, unknown> = { log: (o.log || []).concat([ev]), updated_at: new Date().toISOString() };
    if (ok) { patch.pay_status = "refunded"; patch.status = "cancelled"; }
    await db("rt_orders?id=eq." + id, { method: "PATCH", body: JSON.stringify(patch) });
    return ok ? j({ ok: true, how, desc: res.Description }) : j({ error: "cardcom", how, code: res?.ResponseCode, desc: res?.Description }, 502);
  } catch (e) {
    return j({ error: "server", desc: String((e as Error).message || e).slice(0, 200) }, 500);
  }
});
