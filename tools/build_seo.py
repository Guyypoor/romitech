#!/usr/bin/env python3
"""RomiTech – בניית עמודים סטטיים לגוגל (24/10/2026).

מה נבנה מתוך products.json (לפי ההגדרות ב-CONFIG שב-index.html – אותם מוצרים שמוצגים באתר):
  p/<id>/index.html  – עמוד קבוע לכל מוצר (כותרת, מחיר, מלאי, Product schema, תגיות שיתוף)
  c/<cat>/index.html – עמוד לכל קטגוריה עם קישורים לכל המוצרים בה
  m/<model>/index.html – עמוד לכל דגם מכשיר (למשל "אביזרים ל-iPhone 17 Pro")
  sitemap.xml        – כל העמודים
  feed.xml           – פיד מוצרים ל-Google Merchant Center (RSS 2.0)

הרצה: python3 tools/build_seo.py   (רץ גם אוטומטית ב-GitHub Actions כש-products.json או index.html משתנים)
"""
import html, json, os, re, shutil, sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = 'https://romitech.co.il'
TODAY = date.today().isoformat()
SB_URL = 'https://rtoukdganvoypamxjgwb.supabase.co'
SHIP_FEE, SHIP_FREE = 35, 199
MIN_MODEL = 5
STK = [('במלאי', 'in_stock', 'https://schema.org/InStock'),
       ('מלאי נמוך', 'in_stock', 'https://schema.org/LimitedAvailability'),
       ('אזל מהמלאי', 'out_of_stock', 'https://schema.org/OutOfStock')]
STATIC_PAGES = ['', 'terms.html', 'shipping.html', 'returns.html', 'privacy.html', 'accessibility.html']

e = lambda s: html.escape(str(s), quote=True)


def read_config():
    src = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
    m = re.search(r'const CONFIG\s*=\s*\{(.*?)\n\};', src, re.S)
    if not m:
        sys.exit('CONFIG לא נמצא ב-index.html')
    body = re.sub(r'//[^\n]*', '', m.group(1))
    def val(key, default):
        mm = re.search(r'\b' + key + r'\s*:\s*([^,\n]+)', body)
        if not mm:
            return default
        raw = mm.group(1).strip()
        if raw.startswith('['):
            return re.findall(r"'([^']*)'", raw)
        if raw in ('true', 'false'):
            return raw == 'true'
        return float(raw)
    return {k: val(k, d) for k, d in [('priceMultiplier', 1.0), ('addVat', False), ('vat', 0.18),
            ('hideCats', []), ('hideSup', []), ('hideFlagged', False), ('hideOutOfStock', False)]}


def price_of(agorot, cfg):
    v = agorot / 100 * cfg['priceMultiplier']
    if cfg['addVat']:
        v *= 1 + cfg['vat']
    return round(v, 2)


def money(v):
    return '₪' + (f'{v:,.0f}' if float(v).is_integer() else f'{v:,.2f}')


def valid_gtin(code):
    if not re.fullmatch(r'\d{8}|\d{12,14}', code or ''):
        return False
    c = code.zfill(14)
    if c.startswith(('02', '04', '002')) or c[1] == '2' or set(c) == {'0'}:
        return False  # קידומות פנימיות/מוגבלות שגוגל דוחה
    digits = [int(x) for x in c]
    s = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(digits[:-1]))
    return (10 - s % 10) % 10 == digits[-1]


def slug(s):
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return s or None


HEAD = '''<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self' {sb}; object-src 'none'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests">
<meta name="referrer" content="strict-origin-when-cross-origin">
<script>if(location.protocol==="http:"&&/(^|\\.)romitech\\.co\\.il$/.test(location.hostname))location.replace("https://"+location.host+location.pathname+location.search+location.hash);if(top!==self)top.location=self.location;</script>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="{ogtype}">
<meta property="og:locale" content="he_IL">
<meta property="og:site_name" content="RomiTech">
<meta property="og:title" content="{ogtitle}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{image}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/og.png">
<link rel="stylesheet" href="/fonts/rubik.css">
<link rel="stylesheet" href="/shop-pages.css">
{ld}
</head>
<body>
<a class="skip" href="#main">דילוג לתוכן הראשי</a>
<header class="top">
  <a class="logo" href="/" aria-label="RomiTech – לדף הבית">Romi<b>Tech</b></a>
  <nav aria-label="ניווט"><a href="/#shop">כל המוצרים</a><a href="/shipping.html">משלוחים</a></nav>
</header>
<main id="main" tabindex="-1">
'''

FOOT = '''</main>
<footer>
  <p class="trust">משלוח לכל הארץ עד 7 ימי עסקים · משלוח חינם מעל ₪199 · איסוף עצמי חינם מחנות אייטק, הדקלים 104, פרדס חנה · ביטול עסקה תוך 14 יום לפי חוק הגנת הצרכן</p>
  <nav aria-label="דפי מידע"><a href="/terms.html">תקנון</a><a href="/shipping.html">משלוחים</a><a href="/returns.html">ביטול עסקה והחזרות</a><a href="/privacy.html">מדיניות פרטיות</a><a href="/accessibility.html">הצהרת נגישות</a></nav>
  © 2026 RomiTech · גיא פור יזמות והפצה בע״מ, ח.פ. 517290664
</footer>
{script}
</body>
</html>
'''


def page(title, desc, url, image, body, ld='', ogtype='website', ogtitle=None, script=''):
    head = HEAD.format(sb=SB_URL, title=e(title), desc=e(desc), url=e(url), image=e(image),
                       ld=ld, ogtype=ogtype, ogtitle=e(ogtitle or title))
    return head + body + FOOT.format(script=script)


def ld_json(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace('</', '<\\/') + '</script>'


def img_tag(p, cls='', eager=False):
    if p['img'] is None or p['img'] < 0:
        return f'<span class="noimg {cls}" role="img" aria-label="{e(p["name"])}">Romi<b>Tech</b></span>'
    lz = '' if eager else ' loading="lazy"'
    return f'<img class="{cls}" src="/img/{p["img"]}.webp" alt="{e(p["name"])}"{lz} decoding="async" width="600" height="600">'


def card(p):
    st = STK[p['stock']][0]
    return (f'<li><a class="pc" href="/p/{p["id"]}/"><span class="box">{img_tag(p)}</span>'
            f'<span class="nm">{e(p["name"])}</span>'
            f'<span class="meta"><b class="price">{money(p["price"])}</b><span class="st s{p["stock"]}">{st}</span></span></a></li>')


def describe(p, catname):
    parts = [p['name'] + '.']
    if p['brand']:
        parts.append(f'מותג: {p["brand"]}.')
    parts.append(f'מתאים ל: {p["models"]}.' if p['models'] else f'קטגוריה: {catname}.')
    parts.append('משלוח לכל הארץ עד 7 ימי עסקים (חינם מעל ₪199) או איסוף עצמי חינם מפרדס חנה. ביטול עסקה תוך 14 יום.')
    return ' '.join(parts)


def main():
    cfg = read_config()
    d = json.load(open(os.path.join(ROOT, 'products.json'), encoding='utf-8'))
    cats = d['cats']
    prods = []
    for a in d['p']:
        p = dict(id=a[0], name=a[1].strip(), sku=str(a[2]), brand=(a[3] or '').strip(), cat=a[4],
                 models=(a[5] or '').strip(), agorot=a[6], stock=a[7] if a[7] in (0, 1, 2) else 0,
                 img=a[8], flag=a[9], sup=a[10] or 'M')
        if p['sup'] in cfg['hideSup'] or cats[p['cat']][0] in cfg['hideCats']:
            continue
        if cfg['hideFlagged'] and p['flag']:
            continue
        if cfg['hideOutOfStock'] and p['stock'] == 2:
            continue
        p['price'] = price_of(p['agorot'], cfg)
        if p['price'] <= 0:
            continue
        prods.append(p)

    # ניקוי עמודים ישנים (מוצר שהוסר מהאתר לא נשאר באוויר)
    for sub in ('p', 'c', 'm'):
        shutil.rmtree(os.path.join(ROOT, sub), ignore_errors=True)

    def write(rel, content):
        path = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    by_cat, by_model = {}, {}
    for p in prods:
        by_cat.setdefault(p['cat'], []).append(p)
        if p['models']:
            by_model.setdefault(p['models'], []).append(p)
    model_slug = {}
    for mname, ps in by_model.items():
        s = slug(mname)
        if s and len(ps) >= MIN_MODEL and s not in model_slug.values():
            model_slug[mname] = s

    order = lambda ps: sorted(ps, key=lambda p: (p['stock'] == 2, p['img'] is None or p['img'] < 0, -p['id']))
    urls = [(SITE + '/' + x, '0.5' if x else '1.0') for x in STATIC_PAGES]

    # ---------- עמודי מוצר ----------
    for p in prods:
        catkey, catname = cats[p['cat']][0], cats[p['cat']][1]
        url = f'{SITE}/p/{p["id"]}/'
        image = f'{SITE}/img/{p["img"]}.webp' if p['img'] is not None and p['img'] >= 0 else f'{SITE}/og.png'
        desc = describe(p, catname)
        label, _, schema_av = STK[p['stock']]
        offer = {'@type': 'Offer', 'url': url, 'priceCurrency': 'ILS', 'price': f'{p["price"]:.2f}',
                 'availability': schema_av, 'itemCondition': 'https://schema.org/NewCondition',
                 'seller': {'@type': 'Organization', 'name': 'RomiTech'},
                 'shippingDetails': {'@type': 'OfferShippingDetails',
                     'shippingRate': {'@type': 'MonetaryAmount', 'value': 0 if p['price'] >= SHIP_FREE else SHIP_FEE, 'currency': 'ILS'},
                     'shippingDestination': {'@type': 'DefinedRegion', 'addressCountry': 'IL'},
                     'deliveryTime': {'@type': 'ShippingDeliveryTime',
                         'handlingTime': {'@type': 'QuantitativeValue', 'minValue': 0, 'maxValue': 2, 'unitCode': 'DAY'},
                         'transitTime': {'@type': 'QuantitativeValue', 'minValue': 1, 'maxValue': 5, 'unitCode': 'DAY'}}},
                 'hasMerchantReturnPolicy': {'@type': 'MerchantReturnPolicy', 'applicableCountry': 'IL',
                     'returnPolicyCategory': 'https://schema.org/MerchantReturnFiniteReturnWindow',
                     'merchantReturnDays': 14, 'returnMethod': 'https://schema.org/ReturnByMail',
                     'returnFees': 'https://schema.org/ReturnFeesCustomerResponsibility',
                     'merchantReturnLink': SITE + '/returns.html'}}
        prod_ld = {'@context': 'https://schema.org', '@type': 'Product', 'name': p['name'], 'image': [image],
                   'description': desc, 'sku': p['sku'], 'category': catname, 'offers': offer}
        if p['brand']:
            prod_ld['brand'] = {'@type': 'Brand', 'name': p['brand']}
        if valid_gtin(p['sku']):
            prod_ld['gtin'] = p['sku']
        crumbs = [('RomiTech', SITE + '/'), (catname, f'{SITE}/c/{catkey}/')]
        if p['models'] in model_slug:
            crumbs.append((p['models'], f'{SITE}/m/{model_slug[p["models"]]}/'))
        crumbs.append((p['name'], url))
        bc_ld = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': u} for i, (n, u) in enumerate(crumbs)]}
        rel = [x for x in order(by_cat[p['cat']]) if x['id'] != p['id'] and x['stock'] < 2
               and (not p['models'] or x['models'] == p['models'] or not x['models'])][:8]
        crumb_html = ' › '.join(f'<a href="{e(u.replace(SITE, ""))}">{e(n)}</a>' for n, u in crumbs[:-1])
        spec = ''.join(f'<div><dt>{k}</dt><dd>{v}</dd></div>' for k, v in [
            ('מותג', e(p['brand'])) if p['brand'] else (None, None),
            ('מתאים ל', f'<span dir="ltr">{e(p["models"])}</span>' if p['models'] else 'אוניברסלי'),
            ('קטגוריה', f'<a href="/c/{catkey}/">{e(catname)}</a>'),
            ('מק״ט / ברקוד', f'<span dir="ltr">{e(p["sku"])}</span>')] if k)
        body = f'''<nav class="crumbs" aria-label="מיקום באתר">{crumb_html}</nav>
<article class="pdp" data-sku="{e(p['sku'])}">
  <div class="shot">{img_tag(p, eager=True)}</div>
  <div class="info">
    <h1>{e(p['name'])}</h1>
    <p class="pr"><b class="price">{money(p['price'])}</b> <span class="vat">כולל מע״מ</span> <span class="st s{p['stock']}" id="stk">{label}</span></p>
    <a class="btn" id="buy" href="/#p/{p['id']}"{' aria-disabled="true"' if p['stock'] == 2 else ''}>{'אזל מהמלאי' if p['stock'] == 2 else 'להזמנה באתר'}</a>
    <ul class="perks">
      <li>{'משלוח חינם עד הבית' if p['price'] >= SHIP_FREE else f'משלוח עד הבית ₪{SHIP_FEE} · חינם בהזמנה מעל ₪{SHIP_FREE}'} · עד 7 ימי עסקים</li>
      <li>איסוף עצמי חינם מחנות אייטק, פרדס חנה</li>
      <li>ביטול עסקה תוך 14 יום · <a href="/returns.html">פרטים</a></li>
    </ul>
    <dl class="spec">{spec}</dl>
    <p class="desc">{e(desc)}</p>
  </div>
</article>
'''
        if rel:
            body += f'<section class="more"><h2>עוד ב{e(catname)}</h2><ul class="grid">{"".join(card(x) for x in rel)}</ul></section>\n'
        script = STOCK_JS.replace('__SB__', SB_URL)
        write(f'p/{p["id"]}/index.html', page(f'{p["name"]} – {money(p["price"])} | RomiTech', desc, url, image, body,
                                             ld_json(prod_ld) + '\n' + ld_json(bc_ld), 'product',
                                             ogtitle=f'{p["name"]} – {money(p["price"])}', script=script))
        urls.append((url, '0.6'))

    # ---------- עמודי קטגוריה ----------
    for ci, ps in by_cat.items():
        catkey, catname = cats[ci][0], cats[ci][1]
        ps = order(ps)
        url = f'{SITE}/c/{catkey}/'
        models_here = sorted({p['models'] for p in ps if p['models'] in model_slug})
        chips = ''.join(f'<a href="/m/{model_slug[m]}/" dir="ltr">{e(m)}</a>' for m in models_here)
        desc = f'{catname} ב-RomiTech: {len(ps)} מוצרים, מחירים מ-{money(min(p["price"] for p in ps))}. משלוח לכל הארץ או איסוף עצמי מפרדס חנה.'
        body = (f'<nav class="crumbs" aria-label="מיקום באתר"><a href="/">RomiTech</a></nav>'
                f'<h1>{e(catname)}</h1><p class="lead">{len(ps)} מוצרים · משלוח לכל הארץ · איסוף עצמי מפרדס חנה</p>'
                + (f'<nav class="chips" aria-label="סינון לפי מכשיר">{chips}</nav>' if chips else '')
                + f'<ul class="grid">{"".join(card(p) for p in ps)}</ul>\n')
        ld = ld_json({'@context': 'https://schema.org', '@type': 'CollectionPage', 'name': catname, 'url': url,
                      'mainEntity': {'@type': 'ItemList', 'numberOfItems': len(ps), 'itemListElement': [
                          {'@type': 'ListItem', 'position': i + 1, 'url': f'{SITE}/p/{p["id"]}/'} for i, p in enumerate(ps[:100])]}})
        write(f'c/{catkey}/index.html', page(f'{catname} – RomiTech', desc, url, SITE + '/og.png', body, ld))
        urls.append((url, '0.8'))

    # ---------- עמודי דגם ----------
    for mname, s in model_slug.items():
        ps = order(by_model[mname])
        url = f'{SITE}/m/{s}/'
        groups = {}
        for p in ps:
            groups.setdefault(p['cat'], []).append(p)
        names = '، '.join(cats[c][1] for c in groups)
        desc = f'אביזרים ל-{mname}: {names}. {len(ps)} מוצרים, משלוח לכל הארץ או איסוף עצמי מפרדס חנה.'
        body = (f'<nav class="crumbs" aria-label="מיקום באתר"><a href="/">RomiTech</a></nav>'
                f'<h1>אביזרים ל-<span dir="ltr">{e(mname)}</span></h1><p class="lead">{len(ps)} מוצרים שמתאימים ל-<span dir="ltr">{e(mname)}</span></p>')
        for c, gp in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            body += f'<section><h2>{e(cats[c][1])} ל-<span dir="ltr">{e(mname)}</span></h2><ul class="grid">{"".join(card(p) for p in gp)}</ul></section>\n'
        ld = ld_json({'@context': 'https://schema.org', '@type': 'CollectionPage', 'name': f'אביזרים ל-{mname}', 'url': url})
        write(f'm/{s}/index.html', page(f'אביזרים ל-{mname} – כיסויים, מגני מסך ועוד | RomiTech', desc, url, SITE + '/og.png', body, ld))
        urls.append((url, '0.8'))

    # ---------- sitemap ----------
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f'<url><loc>{e(u)}</loc><lastmod>{TODAY}</lastmod><priority>{pr}</priority></url>' for u, pr in urls]
    sm.append('</urlset>')
    write('sitemap.xml', '\n'.join(sm) + '\n')

    # ---------- פיד Google Merchant Center ----------
    x = lambda s: html.escape(str(s), quote=False)
    items = []
    for p in prods:
        catname = cats[p['cat']][1]
        gt = f'<g:gtin>{p["sku"]}</g:gtin>' if valid_gtin(p['sku']) else '<g:identifier_exists>no</g:identifier_exists>'
        img = f'{SITE}/img/{p["img"]}.webp' if p['img'] is not None and p['img'] >= 0 else None
        if not img:
            continue  # גוגל דוחה מוצר בלי תמונה
        ship = 0 if p['price'] >= SHIP_FREE else SHIP_FEE
        items.append(
            '<item>'
            f'<g:id>RT{p["id"]}</g:id><g:title>{x(p["name"][:150])}</g:title>'
            f'<g:description>{x(describe(p, catname))}</g:description>'
            f'<g:link>{SITE}/p/{p["id"]}/</g:link><g:image_link>{img}</g:image_link>'
            f'<g:availability>{STK[p["stock"]][1]}</g:availability><g:price>{p["price"]:.2f} ILS</g:price>'
            f'<g:condition>new</g:condition>' + (f'<g:brand>{x(p["brand"])}</g:brand>' if p['brand'] else '') + gt +
            f'<g:product_type>{x(catname)}</g:product_type>'
            f'<g:shipping><g:country>IL</g:country><g:price>{ship:.2f} ILS</g:price>'
            '<g:min_handling_time>0</g:min_handling_time><g:max_handling_time>2</g:max_handling_time>'
            '<g:min_transit_time>1</g:min_transit_time><g:max_transit_time>5</g:max_transit_time></g:shipping>'
            '</item>')
    feed = ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0"><channel>'
            f'<title>RomiTech</title><link>{SITE}/</link><description>אביזרי סלולר</description>\n'
            + '\n'.join(items) + '\n</channel></rss>\n')
    write('feed.xml', feed)

    print(f'מוצרים: {len(prods)} · קטגוריות: {len(by_cat)} · דגמים: {len(model_slug)} · בפיד: {len(items)} · '
          f'GTIN תקין: {sum(valid_gtin(p["sku"]) for p in prods)} · כתובות ב-sitemap: {len(urls)}')


# עדכון מלאי חי בעמוד המוצר (אותה פונקציה שהאתר משתמש בה – rt_stock_map, מפתח ציבורי מוגבל ב-RLS)
STOCK_JS = '''<script>(function(){var el=document.querySelector('.pdp');if(!el)return;var sku=el.dataset.sku;
var K='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJ0b3VrZGdhbnZveXBhbXhqZ3diIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE2NzU5NTksImV4cCI6MjEwNzI1MTk1OX0.RSxoPyIPf_KPvwe9rVa2rNsZoSUe5lDxEQmzh14mIFw';
fetch('__SB__/rest/v1/rpc/rt_stock_map',{method:'POST',headers:{apikey:K,Authorization:'Bearer '+K,'Content-Type':'application/json'},body:'{}'})
.then(function(r){return r.ok?r.json():null}).then(function(m){if(!Array.isArray(m))return;var v=null;
m.forEach(function(x){if(String(x[0])===sku)v=x[1]});if(v===null)return;var L=['במלאי','מלאי נמוך','אזל מהמלאי'];
var s=document.getElementById('stk');s.textContent=L[v];s.className='st s'+v;var b=document.getElementById('buy');
if(v===2){b.textContent='אזל מהמלאי';b.setAttribute('aria-disabled','true')}else{b.textContent='להזמנה באתר';b.removeAttribute('aria-disabled')}}).catch(function(){});})();</script>'''

if __name__ == '__main__':
    main()
