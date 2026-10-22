-- RomiTech – אבטחה + מד תנועה (22/10/2026)

-- לפני השינוי: rt_is_admin = exists(profiles where id=auth.uid() and role='admin')
-- 1) מנהל = admin פעיל; אם הוגדר אימות דו-שלבי (TOTP) – חובה כניסה בדרגת aal2
create or replace function public.rt_is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists(select 1 from public.profiles where id = auth.uid() and role = 'admin' and status = 'active')
     and ( coalesce(auth.jwt()->>'aal','aal1') = 'aal2'
           or not exists(select 1 from auth.mfa_factors f where f.user_id = auth.uid() and f.status = 'verified') );
$$;

-- האם למשתמש המחובר יש אימות דו-שלבי פעיל (לפאנל)
create or replace function public.rt_admin_mfa_state() returns jsonb
language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'role_ok', exists(select 1 from public.profiles where id = auth.uid() and role = 'admin' and status = 'active'),
    'has_factor', exists(select 1 from auth.mfa_factors f where f.user_id = auth.uid() and f.status = 'verified'),
    'aal', coalesce(auth.jwt()->>'aal','aal1'));
$$;
revoke all on function public.rt_admin_mfa_state() from public, anon;
grant execute on function public.rt_admin_mfa_state() to authenticated;

-- 2) search_path קבוע לטריגר
alter function public.rt_touch() set search_path = public;

-- 3) הגבלת קצב כללית להזמנות (נגד הצפה במספרי טלפון מתחלפים)
create or replace function public.rt_orders_flood_guard() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if (select count(*) from rt_orders where created_at > now() - interval '10 minutes') >= 30 then
    raise exception 'busy';
  end if;
  return new;
end $$;
revoke all on function public.rt_orders_flood_guard() from public, anon, authenticated;
drop trigger if exists rt_orders_flood_guard on public.rt_orders;
create trigger rt_orders_flood_guard before insert on public.rt_orders
  for each row execute function public.rt_orders_flood_guard();

-- 4) מד תנועה – אנונימי, בלי IP ובלי פרטים אישיים
create table if not exists public.rt_visits (
  id bigserial primary key,
  at timestamptz not null default now(),
  vid text not null,      -- מזהה דפדפן אקראי
  sid text not null,      -- מזהה ביקור (לשונית)
  ev text not null,       -- view | product | cart | checkout | paid
  path text,
  pid int,
  ref text,               -- דומיין מקור (גוגל/פייסבוק/ישיר)
  dev text                -- mobile | tablet | desktop
);
create index if not exists rt_visits_at on public.rt_visits(at);
create index if not exists rt_visits_vid_at on public.rt_visits(vid, at);
alter table public.rt_visits enable row level security;
revoke all on table public.rt_visits from anon, authenticated;
revoke all on sequence public.rt_visits_id_seq from anon, authenticated;

create or replace function public.rt_track(p jsonb) returns void
language plpgsql security definer set search_path = public as $$
declare v text := lower(coalesce(p->>'vid','')); s text := lower(coalesce(p->>'sid','')); e text := coalesce(p->>'ev','');
begin
  if v !~ '^[a-z0-9]{10,32}$' or s !~ '^[a-z0-9]{6,32}$' then return; end if;
  if e not in ('view','product','cart','checkout','paid') then return; end if;
  if (select count(*) from rt_visits where vid = v and at > now() - interval '1 minute') >= 40 then return; end if;
  if (select count(*) from rt_visits where at > now() - interval '1 minute') >= 2000 then return; end if;
  insert into rt_visits(vid, sid, ev, path, pid, ref, dev)
  values (v, s, e,
          left(regexp_replace(coalesce(p->>'path',''), '[^\w\-#/=&.]', '', 'g'), 60),
          case when coalesce(p->>'pid','') ~ '^\d{1,7}$' then (p->>'pid')::int end,
          left(regexp_replace(lower(coalesce(p->>'ref','')), '[^a-z0-9.\-]', '', 'g'), 60),
          case when p->>'dev' in ('mobile','tablet','desktop') then p->>'dev' end);
  if random() < 0.002 then delete from rt_visits where at < now() - interval '400 days'; end if;
end $$;
revoke all on function public.rt_track(jsonb) from public;
grant execute on function public.rt_track(jsonb) to anon, authenticated;

create or replace function public.rt_traffic(p_days int default 14) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare d int := least(greatest(coalesce(p_days,14),1),90);
        tz text := 'Asia/Jerusalem';
        t0 timestamptz := date_trunc('day', now() at time zone tz) at time zone tz;
        since timestamptz := t0 - make_interval(days => d - 1);
        res jsonb;
begin
  if not rt_is_admin() then raise exception 'not_admin'; end if;
  select jsonb_build_object(
    'now', now(),
    'live', (select count(distinct vid) from rt_visits where at > now() - interval '5 minutes'),
    'today', (select jsonb_build_object('visitors', count(distinct vid), 'visits', count(distinct sid),
                     'views', count(*) filter (where ev='view'), 'products', count(*) filter (where ev='product'))
              from rt_visits where at >= t0),
    'days', (select coalesce(jsonb_agg(x order by x->>'d'), '[]') from (
              select jsonb_build_object('d', to_char(g.dd,'YYYY-MM-DD'),
                'visitors', (select count(distinct vid) from rt_visits v where v.at >= g.a and v.at < g.b),
                'views', (select count(*) from rt_visits v where v.ev='view' and v.at >= g.a and v.at < g.b),
                'orders', (select count(*) from rt_orders o where o.status <> 'test' and o.created_at >= g.a and o.created_at < g.b),
                'paid', (select count(*) from rt_orders o where o.status <> 'test' and o.pay_status in ('paid','refunded') and o.created_at >= g.a and o.created_at < g.b)) x
              from (select gd::date dd, (gd::date)::timestamp at time zone tz a, (gd::date + 1)::timestamp at time zone tz b from generate_series((since at time zone tz)::date, (now() at time zone tz)::date, interval '1 day') gd) g) s),
    'hours', (select coalesce(jsonb_agg(jsonb_build_object('h', h, 'visitors', n) order by h), '[]') from (
              select extract(hour from at at time zone tz)::int h, count(distinct vid) n from rt_visits where at >= t0 group by 1) s),
    'funnel', (select jsonb_build_object(
                 'visitors', count(distinct vid),
                 'product', count(distinct vid) filter (where ev='product'),
                 'cart', count(distinct vid) filter (where ev='cart'),
                 'checkout', count(distinct vid) filter (where ev='checkout'),
                 'orders', (select count(*) from rt_orders o where o.status <> 'test' and o.created_at >= since),
                 'paid', (select count(*) from rt_orders o where o.status <> 'test' and o.pay_status in ('paid','refunded') and o.created_at >= since))
               from rt_visits where at >= since),
    'top_products', (select coalesce(jsonb_agg(jsonb_build_object('pid', pid, 'views', n, 'carts', c) order by n desc), '[]') from (
              select pid, count(*) filter (where ev='product') n, count(*) filter (where ev='cart') c
              from rt_visits where at >= since and pid is not null group by pid order by 2 desc, 3 desc limit 10) s),
    'sources', (select coalesce(jsonb_agg(jsonb_build_object('ref', ref, 'visits', n) order by n desc), '[]') from (
              select r ref, count(*) n from (select sid, coalesce(max(nullif(ref,'')),'direct') r from rt_visits where at >= since group by sid) q group by 1 order by 2 desc limit 8) s),
    'devices', (select coalesce(jsonb_agg(jsonb_build_object('dev', dev, 'visitors', n) order by n desc), '[]') from (
              select coalesce(dev,'desktop') dev, count(distinct vid) n from rt_visits where at >= since group by 1) s),
    'pages', (select coalesce(jsonb_agg(jsonb_build_object('path', path, 'views', n) order by n desc), '[]') from (
              select coalesce(nullif(path,''),'#home') path, count(*) n from rt_visits where at >= since and ev='view' group by 1 order by 2 desc limit 8) s)
  ) into res;
  return res;
end $$;
revoke all on function public.rt_traffic(int) from public, anon;
grant execute on function public.rt_traffic(int) to authenticated;
