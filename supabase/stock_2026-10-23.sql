-- RomiTech – מלאי חי (23/10/2026)
-- מקור האמת: קובץ המלאי של הספק (ניל), שמועלה מפאנל הניהול (admin.html → מלאי).
-- המפתח הוא המק"ט/ברקוד (sku) – אותו שדה שיש ב-products.json ובפריטי ההזמנה (rt_orders.items[].sku).
-- מוצר שלא מופיע בטבלה ממשיך להציג את המלאי מ-products.json.
-- להרצה: Supabase → SQL Editor → להדביק את כל הקובץ → Run. אפשר להריץ שוב בלי נזק.

-- 1) טבלת מלאי. הכמויות עצמן לא חשופות לציבור – רק למנהלים.
create table if not exists public.rt_stock (
  sku        text primary key,
  qty        integer not null default 0,
  src        text,
  updated_at timestamptz not null default now()
);
alter table public.rt_stock enable row level security;
drop policy if exists rt_stock_admin on public.rt_stock;
create policy rt_stock_admin on public.rt_stock for all to authenticated
  using (public.rt_is_admin()) with check (public.rt_is_admin());

-- 2) מה שהאתר רואה: רק סטטוס לכל מק"ט – 0 במלאי, 1 מלאי נמוך (3 ומטה), 2 אזל. בלי כמויות.
create or replace function public.rt_stock_map() returns jsonb
language sql stable security definer set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_array(sku, case when qty <= 0 then 2 when qty <= 3 then 1 else 0 end)), '[]'::jsonb)
  from public.rt_stock;
$$;
revoke all on function public.rt_stock_map() from public;
grant execute on function public.rt_stock_map() to anon, authenticated;

-- 3) העלאת קובץ מהפאנל: p_rows = [["sku", qty], ...]. מנהלים בלבד.
create or replace function public.rt_stock_upload(p_rows jsonb, p_src text default null) returns jsonb
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  if not public.rt_is_admin() then raise exception 'forbidden'; end if;
  insert into public.rt_stock (sku, qty, src, updated_at)
  select distinct on (sku) sku, qty, left(p_src, 200), now()
  from (select trim(r->>0) as sku, greatest(0, floor((r->>1)::numeric))::int as qty
        from jsonb_array_elements(p_rows) r
        where coalesce(trim(r->>0), '') <> '' and (r->>1) ~ '^-?[0-9]+(\.[0-9]+)?$') x
  on conflict (sku) do update set qty = excluded.qty, src = excluded.src, updated_at = now();
  get diagnostics n = row_count;
  return jsonb_build_object('saved', n);
end $$;
revoke all on function public.rt_stock_upload(jsonb, text) from public, anon;
grant execute on function public.rt_stock_upload(jsonb, text) to authenticated;

-- 4) הזמנה עם מוצר שאזל (או יותר יחידות ממה שיש) נחסמת כבר בשרת.
--    האתר כבר מציג הודעה מתאימה כשהשגיאה מכילה out_of_stock.
create or replace function public.rt_orders_stock_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare bad text;
begin
  select x.sku into bad
  from (select i->>'sku' as sku, sum(coalesce((i->>'q')::int, 1)) as q
        from jsonb_array_elements(coalesce(to_jsonb(new.items), '[]'::jsonb)) i group by 1) x
  join public.rt_stock s on s.sku = x.sku
  where s.qty < x.q
  limit 1;
  if bad is not null then raise exception 'out_of_stock %', bad; end if;
  return new;
end $$;
drop trigger if exists rt_orders_stock_guard on public.rt_orders;
create trigger rt_orders_stock_guard before insert on public.rt_orders
  for each row execute function public.rt_orders_stock_guard();

-- 5) הזמנה ששולמה מורידה מהמלאי (פעם אחת בלבד, במעבר ל-paid).
create or replace function public.rt_orders_stock_take() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.pay_status = 'paid' and old.pay_status is distinct from 'paid' then
    update public.rt_stock s set qty = greatest(0, s.qty - x.q), updated_at = now()
    from (select i->>'sku' as sku, sum(coalesce((i->>'q')::int, 1)) as q
          from jsonb_array_elements(coalesce(to_jsonb(new.items), '[]'::jsonb)) i group by 1) x
    where s.sku = x.sku;
  end if;
  return new;
end $$;
drop trigger if exists rt_orders_stock_take on public.rt_orders;
create trigger rt_orders_stock_take after update of pay_status on public.rt_orders
  for each row execute function public.rt_orders_stock_take();
