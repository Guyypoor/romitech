# RomiTech
חנות אונליין לאביזרי סלולר (דרופשיפינג מניל ומיאמי).

- `index.html` – האתר (קטלוג מ-`products.json`, תמונות ב-`img/`).
- `admin.html` – פאנל ניהול הזמנות (כניסה עם משתמש הניהול של גיא שליחויות).
- הזמנות נשמרות ב-Supabase (טבלאות `rt_*`, פונקציה `rt_create_order` – המחירים נלקחים מהשרת).
- תשלום באתר: קארדקום (Edge Functions rt-pay / rt-pay-hook / rt-admin-refund).

## אבטחה (22/10/2026)
- ניהול: סיסמה + אימות דו-שלבי (TOTP) חובה. `rt_is_admin()` דורש admin פעיל ו-aal2 כשמוגדר קוד. יציאה אוטומטית אחרי 30 דק' בלי פעילות, הגבלת ניסיונות, הגנה מהטמעה ב-iframe.
- כל הדפים: Content-Security-Policy (מקורות מותרים בלבד), referrer מוגבל. ספריית Supabase מאוחסנת באתר (`vendor/`) ולא מ-CDN חיצוני.
- מסד: הגבלת קצב כללית להזמנות (30 ל-10 דק'), `rt_touch` עם search_path קבוע. Edge Functions: CORS רק לדומיין האתר, rt-pay – עד 15 ניסיונות ו-48 שעות להזמנה.
- SQL: `supabase/security_traffic_2026-10-22.sql`.

## מד תנועה
- האתר שולח אירועים אנונימיים ל-`rt_track` (view/product/cart/checkout/paid; מזהה אקראי בדפדפן, בלי IP). בוטים לא נספרים.
- טבלה `rt_visits` חסומה לציבור; פאנל הניהול קורא סיכום מ-`rt_traffic(days)` (רק מנהל). לשונית "תנועה באתר" ב-admin.html.
