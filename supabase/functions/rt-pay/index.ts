// RomiTech – יצירת דף תשלום בקארדקום (LowProfile) להזמנה קיימת. 22/10/2026
// קלט: POST {id:"RT-123456", phone:"05XXXXXXXX"}. הסכום והפריטים נלקחים מהשרת (rt_orders), לא מהדפדפן.
// 23/10/2026: חובה טלפון שתואם להזמנה – אחרת מי שמנחש מספר הזמנה היה מקבל דף תשלום עם פרטי הלקוח.
const SB = Deno.env.get("SUPABASE_URL")!;
const SR = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const TERM = Number(Deno.env.get("CARDCOM_TERMINAL"));
const API = Deno.env.get("CARDCOM_API_NAME")!;
const SITE = "https://romitech.co.il/";
// אבטחה 22/10/2026: רק האתר שלנו יכול לקרוא לפונקציה מדפדפן
const ORIGINS = ["https://romitech.co.il", "https://www.romitech.co.il", "https://guyypoor.github.io"];
let CORS: Record<string, string> = {};
const cors = (req: Request) => { const o = req.headers.get("origin") || ""; CORS = { "Access-Control-Allow-Origin": ORIGINS.includes(o) ? o : ORIGINS[0], "Vary": "Origin", "Access-Control-Allow-Headers": "authorization, apikey, content-type", "Access-Control-Allow-Methods": "POST, OPTIONS" }; };
const j = (o: unknown, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { ...CORS, "Content-Type": "application/json", "Cache-Control": "no-store" } });

async function db(path: string, init: RequestInit = {}) {
  const r = await fetch(SB + "/rest/v1/" + path, { ...init, headers: { apikey: SR, Authorization: "Bearer " + SR, "Content-Type": "application/json", Prefer: "return=representation", ...(init.headers || {}) } });
  const t = await r.text();
  if (!r.ok) throw new Error("db " + r.status + " " + t.slice(0, 200));
  return t ? JSON.parse(t) : null;
}

Deno.serve(async (req) => {
  cors(req);
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return j({ error: "method" }, 405);
  try {
    const { id, method, phone } = await req.json();
    if (!/^RT-\d{6}$/.test(String(id || ""))) return j({ error: "bad_id" }, 400);
    const rows = await db("rt_orders?id=eq." + id + "&select=*");
    const o = rows && rows[0];
    const digits = (v: unknown) => String(v || "").replace(/\D/g, "").replace(/^972/, "0");
    if (!o || !digits(phone) || digits(phone) !== digits(o.phone)) return j({ error: "not_found" }, 404);
    if (o.pay_status === "paid") return j({ error: "already_paid" }, 409);
    if (o.status === "cancelled" || o.status === "test") return j({ error: "closed" }, 409);
    // נגד שימוש לרעה: דף תשלום רק להזמנה מהיומיים האחרונים, ועד 15 ניסיונות להזמנה
    if (Date.now() - new Date(o.created_at).getTime() > 48 * 3600 * 1000) return j({ error: "expired" }, 409);
    if ((o.log || []).filter((e: any) => e.ev === "pay_create").length >= 15) return j({ error: "too_many" }, 429);
    const total = Math.round(Number(o.total) * 100) / 100;
    const products = (o.items || []).map((i: any) => ({ ProductID: String(i.sku), Description: String(i.name || i.sku).slice(0, 200), Quantity: Number(i.q), UnitCost: Number(i.price) }));
    if (Number(o.ship_fee) > 0) products.push({ ProductID: "SHIP", Description: "משלוח עד הבית", Quantity: 1, UnitCost: Number(o.ship_fee) });
    const hook = SB + "/functions/v1/rt-pay-hook";
    const body = {
      TerminalNumber: TERM, ApiName: API, Operation: "ChargeOnly", ReturnValue: o.id, Amount: total,
      SuccessRedirectUrl: SITE + "?pay=ok&o=" + o.id, FailedRedirectUrl: SITE + "?pay=fail&o=" + o.id, CancelRedirectUrl: SITE + "?pay=cancel&o=" + o.id,
      WebHookUrl: hook, ProductName: "הזמנה " + o.id + " – RomiTech", Language: "he", ISOCoinId: 1,
      UIDefinition: { CardOwnerNameValue: o.name || "", CardOwnerPhoneValue: o.phone || "", CardOwnerEmailValue: o.email || "", IsCardOwnerPhoneRequired: true },
      Document: { DocumentTypeToCreate: "TaxInvoiceAndReceipt", Name: o.name || "לקוח", Email: o.email || "", IsSendByEmail: !!o.email, Mobile: o.phone || "", City: o.city || "", AddressLine1: o.street || "", ExternalId: o.id, Products: products, Language: "he" },
    };
    const r = await fetch("https://secure.cardcom.solutions/api/v11/LowProfile/Create", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const res = await r.json();
    const log = (o.log || []).concat([{ at: new Date().toISOString(), ev: "pay_create", code: res.ResponseCode, desc: res.Description, lp: res.LowProfileId }]);
    await db("rt_orders?id=eq." + o.id, { method: "PATCH", body: JSON.stringify({ pay_method: ["apple", "card", "bit", "google", "paypal"].includes(method) ? method : o.pay_method, pay_ref: res.LowProfileId || o.pay_ref, log, updated_at: new Date().toISOString() }) });
    if (res.ResponseCode !== 0) return j({ error: "cardcom", code: res.ResponseCode, desc: res.Description }, 502);
    return j({ url: res.Url, bit: res.UrlToBit || null, id: o.id, total });
  } catch (e) {
    console.error("rt-pay", e);
    return j({ error: "server" }, 500);
  }
});
