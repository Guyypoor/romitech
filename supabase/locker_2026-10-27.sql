-- 27/10/2026 – משלוח ללוקר / נקודת איסוף (הוחל ב-Supabase דרך Management API מהדשבורד בכרום)
-- 1) ship_method מקבל גם 'locker'
alter table public.rt_orders drop constraint rt_orders_ship_method_check;
alter table public.rt_orders add constraint rt_orders_ship_method_check
  check (ship_method = any (array['pickup'::text,'home'::text,'locker'::text]));

-- 2) rt_create_order – השינויים בגוף הפונקציה (שאר הפונקציה ללא שינוי):
--   if ship not in ('pickup','home','locker') then raise exception 'bad_ship'; end if;
--   if ship in ('home','locker') and (city ריק או street ריק) then raise exception 'bad_address'; end if;
--   if ship in ('home','locker') then
--     if ship = 'locker' then
--       select (v#>>'{}')::numeric into fee from rt_settings where k='ship_locker_fee';
--       if fee is null then raise exception 'bad_ship'; end if;   -- לוקר כבוי כל עוד אין מחיר בפאנל
--     else
--       select (v#>>'{}')::numeric into fee from rt_settings where k='ship_home_fee'; fee := coalesce(fee,35);
--     end if;
--     ... משלוח חינם מעל ship_free_over – חל גם על לוקר
--   insert: city/street נשמרים גם ל-locker.
-- נבדק (טרנזקציה שבוטלה): בלי מחיר → bad_ship; מחיר 15 → ₪49.90+15=64.90; מעל 199 → 0; home → +35; pickup → 0.
