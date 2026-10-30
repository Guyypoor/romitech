// RomiTech – Webhook מקארדקום אחרי תשלום. לא סומכים על מה שנשלח: מאמתים מול GetLpResult. 22/10/2026
const SB = Deno.env.get("SUPABASE_URL")!;
const SR = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const TERM = Number(Deno.env.get("CARDCOM_TERMINAL"));
const API = Deno.env.get("CARDCOM_API_NAME")!;

async function db(path: string, init: RequestInit = {}) {
  const r = await fetch(SB + "/rest/v1/" + path, { ...init, headers: { apikey: SR, Authorization: "Bearer " + SR, "Content-Type": "application/json", Prefer: "return=representation", ...(init.headers || {}) } });
  const t = await r.text();
  if (!r.ok) throw new Error("db " + r.status + " " + t.slice(0, 200));
  return t ? JSON.parse(t) : null;
}

Deno.serve(async (req) => {
  let lp = "";
  try {
    const txt = await req.text();
    try { lp = JSON.parse(txt).LowProfileId || ""; } catch { lp = new URLSearchParams(txt).get("LowProfileId") || new URL(req.url).searchParams.get("LowProfileId") || ""; }
    if (!/^[0-9a-fA-F-]{20,}$/.test(lp)) return new Response("no lp", { status: 400 });
    const r = await fetch("https://secure.cardcom.solutions/api/v11/LowProfile/GetLpResult", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ TerminalNumber: TERM, ApiName: API, LowProfileId: lp }) });
    const res = await r.json();
    const id = String(res.ReturnValue || "");
    const rows = await db("rt_orders?id=eq." + encodeURIComponent(id) + "&select=id,total,pay_status,log");
    const o = rows && rows[0];
    if (!o) return new Response("no order", { status: 200 });
    // 30/10/2026: הזמנה ששולמה או הוחזרה – לא נוגעים. אחרת שליחה חוזרת של LowProfileId ישן הייתה מחזירה הזמנה מזוכה ל"שולם" ומורידה מלאי שוב.
    if (o.pay_status === "paid" || o.pay_status === "refunded") return new Response("ok", { status: 200 });
    const amt = Number(res.TranzactionInfo?.Amount ?? NaN);
    const ok = res.ResponseCode === 0 && res.TranzactionId > 0;
    const match = ok && Math.abs(amt - Number(o.total)) < 0.01;
    const ev = { at: new Date().toISOString(), ev: "pay_hook", code: res.ResponseCode, desc: res.Description, tx: res.TranzactionId, amount: amt, doc: res.DocumentInfo?.DocumentNumber ?? null, doc_url: res.DocumentInfo?.DocumentUrl ?? null, lp };
    const patch: Record<string, unknown> = { log: (o.log || []).concat([ev]), updated_at: new Date().toISOString(), pay_status: match ? "paid" : ok ? "amount_mismatch" : "failed" };
    if (ok) patch.pay_ref = String(res.TranzactionId);
    await db("rt_orders?id=eq." + encodeURIComponent(id), { method: "PATCH", body: JSON.stringify(patch) });
    return new Response("ok", { status: 200 });
  } catch (e) {
    return new Response("err " + String((e as Error).message || e).slice(0, 100), { status: 500 });
  }
});
