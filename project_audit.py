# -*- coding: utf-8 -*-
"""
project_audit.py — ممیزی پروژه (فقط خواندنی)

سؤال: «ایراد پروژه کجاست که بعد از چند ماه پیشرفتی نداشته؟»
این برنامه جواب را از داده‌ی خود پروژه می‌سنجد، نه از حدس:

  بخش ۱  بنیان داده: چند درصد تاریخچه قابل راستی‌آزمایی است؟ کدام روزها ناقص بوده‌اند؟
  بخش ۲  لاگ‌ها: سیکل‌های هر روز، خطای سرور بورس، قطع شبکه
  بخش ۳  دفتر معاملات: ورود نامعتبر، موقعیت‌های بیش از حد باز، ناسازگاری ثبت
  بخش ۴  آزمون برتری: آیا سیگنال‌های ربات از انتخاب تصادفی قرارداد بهتر بوده‌اند؟
          (نرخ رسیدن به +TARGET_PCT٪ در HORIZON_DAYS روز، با فاصله‌ی اطمینان و آزمون دوجمله‌ای)
          و برای تشخیص یک برتری مشخص چند معامله‌ی دیگر لازم است
  بخش ۵  رانش قوانین: هدف و حد ضرر ثبت‌شده در هر هفته چقدر عوض شده؟
  بخش ۶  جمع‌بندی بر پایه‌ی اعداد همین اجرا

ویژگی‌ها:
  - هیچ دیتابیس معاملاتی را تغییر نمی‌دهد (اتصال فقط‌خواندنی)
  - هر بخش جدا در try/except است؛ خطای یک بخش بقیه را متوقف نمی‌کند
  - لاگ هم در فایل (audit_output/audit_<تاریخ>.log) و هم در دیتابیس جدا (audit_output/audit.db)
  - نتیجه‌ی عددی هر اجرا در audit.db ذخیره می‌شود تا روند هفته‌ها قابل مقایسه باشد
  - حالت‌های خاص: قیمت صفر/منفی/NaN، داده‌ی خالی، جدول یا ستون ناموجود، دیتابیس خراب یا قفل،
    حروف عربی/فارسی در نام نماد، ارقام فارسی، تقسیم بر صفر

اجرا (کنار فایل‌های .db، ترجیحاً با ربات بسته یا باز؛ تفاوتی ندارد):
    python project_audit.py
"""
from __future__ import annotations

import bisect
import contextlib
import logging
import math
import re
import sqlite3
import statistics
import sys
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

VERSION = "1.0"

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
LOG_DIR = "logs"
OUT_DIR = "audit_output"

HISTORY_START = "2026-08-01"     # شروع بررسی کلی داده
RELIABLE_START = "2026-11-01"    # از این روز، زمان آخرین معامله و تعداد معامله ثبت می‌شود
MIN_OPTION_PRICE = 10.0
MIN_TRADES = 5
HORIZON_DAYS = 2
TARGET_PCT = 20.0
HOLD_LIMIT_DAYS = 2
MARKET_OPEN = "08:55"
MARKET_CLOSE = "12:35"
UPLIFT_TO_DETECT = 0.10          # برتری مورد نظر برای محاسبه‌ی حجم نمونه (۱۰ واحد درصد)

log = logging.getLogger("project_audit")

# ----------------------------------------------------------------------------
# ابزارهای کمکی: نرمال‌سازی متن، عدد، زمان
# ----------------------------------------------------------------------------
_AR2FA = str.maketrans({"ي": "ی", "ى": "ی", "ئ": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه",
                        "أ": "ا", "إ": "ا", "ؤ": "و"})
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_STRIP = {ord(c): None for c in "\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u00a0 \t\r\n"}


def norm_sym(value) -> str:
    """نام نماد را برای تطبیق یکسان می‌کند (ي/ك عربی، ارقام فارسی، فاصله و نیم‌فاصله)."""
    if value is None:
        return ""
    try:
        return str(value).translate(_AR2FA).translate(_DIGITS).translate(_STRIP)
    except Exception:  # noqa: BLE001 - هر مقدار عجیبی فقط به رشته‌ی خالی تبدیل می‌شود
        return ""


def safe_float(value, default=None):
    """تبدیل ایمن به عدد؛ None، متن، NaN و بی‌نهایت به default می‌روند."""
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return default
        if isinstance(value, (int, float)):
            v = float(value)
        else:
            s = str(value).translate(_DIGITS).replace(",", "").replace("٬", "").replace("٫", ".").strip()
            if s == "":
                return default
            v = float(s)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (ValueError, TypeError, OverflowError):
        return default


def safe_div(a, b, default=None):
    """تقسیم ایمن؛ مخرج صفر یا نامعتبر به default می‌رود."""
    a = safe_float(a)
    b = safe_float(b)
    if a is None or b is None or b == 0:
        return default
    return a / b


def parse_ts(value):
    """زمان را از چند قالب رایج می‌خواند؛ نامعتبر = None."""
    if value is None:
        return None
    text = str(value).strip()
    for fmt, size in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16)):
        try:
            return datetime.strptime(text[:size], fmt)
        except (ValueError, TypeError):
            continue
    return None


def fmt_pct(x, digits=0):
    return "؟" if x is None else f"{x * 100:.{digits}f}٪"


# ----------------------------------------------------------------------------
# آمار: فاصله‌ی ویلسون، آزمون دوجمله‌ای دقیق، حجم نمونه
# ----------------------------------------------------------------------------
def wilson(k: int, n: int, z: float = 1.96):
    if n <= 0:
        return None, None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(max(0.0, p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _log_pmf(i: int, n: int, p: float) -> float:
    return (math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
            + i * math.log(p) + (n - i) * math.log1p(-p))


def binom_sf(k: int, n: int, p: float):
    """P(X >= k) برای X ~ Binomial(n, p)."""
    if n <= 0 or p is None:
        return None
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    total = 0.0
    for i in range(k, n + 1):
        total += math.exp(_log_pmf(i, n, p))
    return min(1.0, total)


def binom_cdf(k: int, n: int, p: float):
    """P(X <= k)."""
    if n <= 0 or p is None:
        return None
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    sf = binom_sf(k + 1, n, p)
    return None if sf is None else max(0.0, 1.0 - sf)


def required_n(p0, delta=UPLIFT_TO_DETECT, z_alpha=1.645, z_beta=0.8416):
    """حداقل تعداد معامله برای تشخیص برتری delta نسبت به نرخ پایه‌ی p0 (آزمون یک‌طرفه، توان ۸۰٪)."""
    if p0 is None:
        return None
    p0c = min(max(p0, 0.02), 0.98)
    p1 = min(p0c + delta, 0.99)
    if p1 <= p0c:
        return None
    num = (z_alpha * math.sqrt(p0c * (1 - p0c)) + z_beta * math.sqrt(p1 * (1 - p1))) ** 2
    return int(math.ceil(num / (p1 - p0c) ** 2))


# ----------------------------------------------------------------------------
# دیتابیس
# ----------------------------------------------------------------------------
def open_ro(path: str) -> sqlite3.Connection:
    """اتصال فقط‌خواندنی. FileNotFoundError اگر فایل نباشد؛ sqlite3.Error اگر خراب باشد."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        conn.execute("PRAGMA query_only=ON")
        # اولین خواندن واقعی؛ فایل غیر SQLite یا خراب همین‌جا خطای DatabaseError می‌دهد
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except sqlite3.Error:
        conn.close()
        raise
    return conn


def q(conn, sql: str, params=(), retries: int = 4, delay: float = 0.5):
    """اجرای کوئری با تلاش دوباره در صورت قفل بودن دیتابیس (ربات هم‌زمان می‌نویسد)."""
    last = None
    for attempt in range(retries):
        try:
            return conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            text = str(exc).lower()
            if "locked" in text or "busy" in text:
                last = exc
                log.warning("دیتابیس قفل است؛ تلاش %s از %s", attempt + 1, retries)
                time.sleep(delay * (attempt + 1))
                continue
            raise
    raise last if last else sqlite3.OperationalError("database is locked")


def table_columns(conn, table: str) -> set:
    try:
        return {row[1] for row in q(conn, f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def open_db_or_report(audit, name: str, path: str):
    """دیتابیس را باز می‌کند؛ اگر نشد، دلیل را گزارش و None برمی‌گرداند."""
    try:
        return open_ro(path)
    except FileNotFoundError:
        audit.out(f"   {name}: فایل {path} پیدا نشد")
    except sqlite3.Error as exc:
        log.error("%s: باز کردن دیتابیس ناموفق: %s", name, exc)
        audit.out(f"   {name}: دیتابیس باز نشد ({type(exc).__name__})")
    return None


# ----------------------------------------------------------------------------
# لاگ و گزارش
# ----------------------------------------------------------------------------
class SqliteLogHandler(logging.Handler):
    """لاگ را در دیتابیس جدا هم می‌نویسد؛ هرگز استثنا بالا نمی‌دهد."""

    def __init__(self, path: Path):
        super().__init__()
        self.path = str(path)
        try:
            with contextlib.closing(sqlite3.connect(self.path, timeout=5)) as c:
                c.execute("CREATE TABLE IF NOT EXISTS audit_log("
                          "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, level TEXT, message TEXT)")
                c.commit()
        except Exception:  # noqa: BLE001
            pass

    def emit(self, record):
        try:
            with contextlib.closing(sqlite3.connect(self.path, timeout=5)) as c:
                c.execute("INSERT INTO audit_log(ts, level, message) VALUES (?,?,?)",
                          (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), record.levelname, self.format(record)))
                c.commit()
        except Exception:  # noqa: BLE001
            pass


def setup_logging() -> Path:
    out_dir = Path(OUT_DIR)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        out_dir = Path(".")
    log.setLevel(logging.DEBUG)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    try:
        fh = logging.FileHandler(out_dir / f"audit_{datetime.now():%Y-%m-%d}.log", encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass
    dh = SqliteLogHandler(out_dir / "audit.db")
    dh.setFormatter(fmt)
    dh.setLevel(logging.INFO)
    log.addHandler(dh)
    return out_dir


class Audit:
    def __init__(self):
        self.lines: list = []
        self.results: list = []
        self.failures: list = []
        self.facts: dict = {}
        # شناسه‌ی یکتای هر اجرا (با میکروثانیه)، تا نتایج دو اجرای نزدیک به هم قاطی نشوند
        self.run_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    def out(self, text: str = ""):
        try:
            print(text)
        except Exception:  # noqa: BLE001 - کنسول‌هایی که فارسی را نمی‌پذیرند
            try:
                print(text.encode("ascii", "replace").decode("ascii"))
            except Exception:  # noqa: BLE001
                pass
        self.lines.append(text)

    def record(self, section: str, key: str, value):
        self.results.append((section, key, "" if value is None else str(value)))

    def run_section(self, title: str, fn):
        self.out("")
        self.out("=" * 72)
        self.out(title)
        self.out("=" * 72)
        log.info("شروع بخش: %s", title)
        try:
            fn(self)
            log.info("پایان بخش: %s", title)
        except Exception as exc:  # noqa: BLE001 - هر بخش ایزوله است
            log.error("خطا در بخش %s: %s\n%s", title, exc, traceback.format_exc())
            self.failures.append(title)
            self.out(f"⚠️ این بخش با خطا متوقف شد: {type(exc).__name__}: {exc} (جزئیات در لاگ)")


# ----------------------------------------------------------------------------
# بخش ۱: بنیان داده
# ----------------------------------------------------------------------------
def section_data(audit: Audit):
    audit.facts.setdefault("verifiable", {})
    audit.facts.setdefault("partial_days", [])
    in_mkt = f"substr(time,12,5) BETWEEN '{MARKET_OPEN}' AND '{MARKET_CLOSE}'"
    for name, path in DBS:
        conn = open_db_or_report(audit, name, path)
        if conn is None:
            continue
        try:
            cols = table_columns(conn, "options")
            if "time" not in cols:
                audit.out(f"   {name}: جدول options یا ستون time موجود نیست")
                continue
            has_pf = "price_fresh" in cols
            has_pt = "price_time" in cols
            sql = ("SELECT substr(time,1,10) AS d, COUNT(*), "
                   f"SUM(CASE WHEN {in_mkt} THEN 1 ELSE 0 END), "
                   f"COUNT(DISTINCT CASE WHEN {in_mkt} THEN substr(time,1,16) END), "
                   + (f"SUM(CASE WHEN {in_mkt} AND price_fresh=1 THEN 1 ELSE 0 END), " if has_pf else "0, ")
                   + ("SUM(CASE WHEN price_time IS NOT NULL AND TRIM(price_time)<>'' THEN 1 ELSE 0 END) "
                      if has_pt else "0 ")
                   + "FROM options WHERE time>=? GROUP BY d ORDER BY d")
            rows = q(conn, sql, (HISTORY_START,))
            if not rows:
                audit.out(f"   {name}: از {HISTORY_START} هیچ ردیفی در options نیست")
                continue
            total = sum(int(r[1] or 0) for r in rows)
            verifiable = sum(int(r[5] or 0) for r in rows)
            share = safe_div(verifiable, total)
            first_pt = next((r[0] for r in rows if (r[5] or 0) > 0), None)
            audit.facts["verifiable"][name] = share
            audit.record("data", f"{name}.verifiable_share", share)
            audit.out(f"— {name} —")
            audit.out(f"   ردیف‌های options از {HISTORY_START}: {total} | دارای زمان آخرین معامله "
                      f"(قابل راستی‌آزمایی): {verifiable} ({fmt_pct(share)})")
            audit.out(f"   اولین روز با زمان آخرین معامله: {first_pt or 'هرگز'}")

            reliable = [r for r in rows if r[0] >= RELIABLE_START]
            snaps_list = [int(r[3] or 0) for r in reliable if (r[3] or 0) > 0]
            cps_list = [safe_div(r[2], r[3]) for r in reliable if (r[3] or 0) > 0]
            cps_list = [c for c in cps_list if c is not None]
            med_snaps = statistics.median(snaps_list) if snaps_list else None
            med_cps = statistics.median(cps_list) if cps_list else None
            audit.out(f"   {'روز':<11}{'نمونه‌ی ساعت بازار':>18}{'قرارداد در هر نمونه':>20}{'تازه':>8}  وضعیت")
            for d, n, mkt_rows, snaps, fresh, _wpt in reliable:
                snaps = int(snaps or 0)
                cps = safe_div(mkt_rows, snaps)
                fresh_share = safe_div(fresh, mkt_rows)
                flag = ""
                if snaps == 0:
                    flag = "بدون نمونه در ساعت بازار"
                elif (med_snaps and snaps < 0.5 * med_snaps) or (med_cps and cps is not None and cps < 0.6 * med_cps):
                    flag = "⚠️ ناقص"
                if flag:
                    audit.facts["partial_days"].append(f"{name} {d}")
                cps_txt = "؟" if cps is None else f"{cps:.0f}"
                audit.out(f"   {d:<11}{snaps:>18}{cps_txt:>20}{fmt_pct(fresh_share):>8}  {flag}")
        finally:
            conn.close()


# ----------------------------------------------------------------------------
# بخش ۲: لاگ‌ها
# ----------------------------------------------------------------------------
_LOG_FILE_RE = re.compile(r"^ahram_pro_(\d{4}-\d{2}-\d{2})\.log$")
_CYCLE_RE = re.compile(r"#\d+\s*\|\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}")
_SERVER_RE = re.compile(r"(SERVER ERROR\s*[:(]|HTTP 5\d\d|ERROR: 5\d\d)")
_NET_RE = re.compile(r"(timed out|Max retries exceeded|CONNECTION ERROR)", re.IGNORECASE)


def section_logs(audit: Audit):
    folder = Path(LOG_DIR)
    if not folder.is_dir():
        audit.out(f"پوشه‌ی {LOG_DIR} پیدا نشد")
        return
    per_day = {}
    for path in sorted(folder.iterdir()):
        m = _LOG_FILE_RE.match(path.name)
        if not m or m.group(1) < RELIABLE_START:
            continue
        cycles = server = net = 0
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if _CYCLE_RE.search(line):
                        cycles += 1
                    if _SERVER_RE.search(line):
                        server += 1
                    if _NET_RE.search(line):
                        net += 1
        except OSError as exc:
            log.error("خواندن لاگ %s ناموفق: %s", path.name, exc)
            audit.out(f"   {path.name}: خواندن ناموفق ({type(exc).__name__})")
            continue
        per_day[m.group(1)] = (cycles, server, net)
    if not per_day:
        audit.out(f"لاگی از {RELIABLE_START} به بعد پیدا نشد")
        return
    audit.out(f"   {'روز':<11}{'سیکل':>6}{'خطای سرور (۵xx)':>18}{'خطای شبکه/تایم‌اوت':>22}")
    noisy_days = []
    for day, (cycles, server, net) in per_day.items():
        audit.out(f"   {day:<11}{cycles:>6}{server:>18}{net:>22}")
        audit.record("logs", f"{day}.cycles", cycles)
        audit.record("logs", f"{day}.server_errors", server)
        audit.record("logs", f"{day}.net_errors", net)
        if server + net >= 20:
            noisy_days.append(day)
    audit.facts["noisy_days"] = noisy_days
    audit.out("   توجه: شمارش سیکل شامل اجرای --test هم می‌شود؛ شمارش خطا بر حسب خط لاگ است.")


# ----------------------------------------------------------------------------
# بخش ۳: دفتر معاملات
# ----------------------------------------------------------------------------
def section_ledger(audit: Audit):
    totals = Counter()
    overdue_all = []
    for name, path in DBS:
        conn = open_db_or_report(audit, name, path)
        if conn is None:
            continue
        try:
            cols = table_columns(conn, "signal_history")
            need = {"id", "time", "signal_type", "option_price", "position_id"}
            if not need <= cols:
                audit.out(f"   {name}: جدول signal_history یا ستون‌های لازم موجود نیست")
                continue
            sel = ("WITH b AS (SELECT position_id, MIN(id) AS f, MAX(id) AS l, COUNT(*) AS n, "
                   "MIN(option_price) AS mn, MAX(option_price) AS mx FROM signal_history "
                   "WHERE position_id IS NOT NULL AND signal_type IN ('BUY_CALL','BUY_PUT') GROUP BY position_id) "
                   "SELECT b.position_id, b.n, b.mn, b.mx, f.time, f.option_price, "
                   + ("f.option_symbol" if "option_symbol" in cols else "NULL") + ", "
                   + ("l.outcome" if "outcome" in cols else "NULL") + ", "
                   + ("l.outcome_time" if "outcome_time" in cols else "NULL")
                   + " FROM b JOIN signal_history f ON f.id=b.f JOIN signal_history l ON l.id=b.l WHERE f.time>=?")
            rows = q(conn, sel, (RELIABLE_START,))
            ref = None
            try:
                latest = q(conn, "SELECT MAX(time) FROM options")
                ref = parse_ts(latest[0][0]) if latest else None
            except sqlite3.Error:
                ref = None
            ref = ref or datetime.now()
            n_pos = len(rows)
            bad_entry = spread = no_out_time = 0
            overdue = []
            n_rows = 0
            for pid, n, mn, mx, t0, entry, osym, outcome, out_time in rows:
                n_rows += int(n or 0)
                e = safe_float(entry)
                if e is None or e < MIN_OPTION_PRICE:
                    bad_entry += 1
                ratio = safe_div(mx, mn)
                if ratio is not None and ratio > 1.15:
                    spread += 1
                if outcome in ("WIN", "LOSS", "BREAK_EVEN") and not out_time:
                    no_out_time += 1
                t_entry = parse_ts(t0)
                if outcome in ("PENDING", "T1_HIT") and t_entry is not None:
                    age = (ref - t_entry).total_seconds() / 86400
                    if age > HOLD_LIMIT_DAYS:
                        overdue.append((osym, t0, outcome, age))
            totals["pos"] += n_pos
            totals["rows"] += n_rows
            totals["bad_entry"] += bad_entry
            totals["spread"] += spread
            totals["no_out_time"] += no_out_time
            overdue_all.extend((name,) + o for o in overdue)
            audit.out(f"— {name} —")
            audit.out(f"   پوزیشن‌ها از {RELIABLE_START}: {n_pos} | ردیف‌های سیگنال: {n_rows} "
                      f"(میانگین {safe_div(n_rows, n_pos, 0):.1f} ردیف برای هر پوزیشن)")
            audit.out(f"   ورود نامعتبر (<{MIN_OPTION_PRICE:.0f} ریال): {bad_entry} | "
                      f"قیمت ورود ناهم‌خوان بین ردیف‌های یک پوزیشن (>۱۵٪): {spread} | "
                      f"بسته بدون زمان خروج: {no_out_time}")
            audit.out(f"   باز بیش از {HOLD_LIMIT_DAYS} روز: {len(overdue)}")
        finally:
            conn.close()
    for name, sym, t0, outcome, age in overdue_all[:10]:
        audit.out(f"      {name} | {sym} | ورود {t0} | {outcome} | {age:.1f} روز")
    audit.facts["overdue"] = len(overdue_all)
    audit.facts["ledger"] = dict(totals)
    for key, value in totals.items():
        audit.record("ledger", key, value)
    audit.record("ledger", "overdue_open", len(overdue_all))


# ----------------------------------------------------------------------------
# بخش ۴: آزمون برتری سیگنال‌ها نسبت به انتخاب تصادفی
# ----------------------------------------------------------------------------
def build_series(conn, cols: set):
    """سری قیمت تازه و نقدشونده‌ی هر قرارداد: کلید نرمال‌شده -> {t, p, type}."""
    if "price_fresh" not in cols:
        return {}
    has_trades = "trades_count" in cols
    sql = ("SELECT time, symbol, option_price, price_fresh, "
           + ("trades_count" if has_trades else "NULL") + ", "
           + ("volume" if "volume" in cols else "NULL") + ", "
           + ("option_type" if "option_type" in cols else "NULL")
           + " FROM options WHERE time>=? ORDER BY id")
    raw = defaultdict(list)
    types = {}
    for t, sym, price, fresh, trades, vol, typ in q(conn, sql, (RELIABLE_START,)):
        p = safe_float(price)
        dt = parse_ts(t)
        if p is None or p < MIN_OPTION_PRICE or dt is None or fresh != 1:
            continue
        if has_trades:
            tr = safe_float(trades)
            if tr is None or tr < MIN_TRADES:
                continue
        else:
            v = safe_float(vol)
            if v is None or v <= 0:
                continue
        key = norm_sym(sym)
        if not key:
            continue
        raw[key].append((dt, p))
        types[key] = str(typ or "UNK").strip().upper()
    series = {}
    for key, pts in raw.items():
        pts.sort(key=lambda x: x[0])
        series[key] = {"t": [x[0] for x in pts], "p": [x[1] for x in pts], "type": types.get(key, "UNK")}
    return series


def reached(ser: dict, t0: datetime, p0: float, pct: float):
    """آیا قیمت در HORIZON_DAYS بعد از t0 به p0*(1+pct%) رسیده؟ None = داده‌ی بعدی نیست."""
    times, prices = ser["t"], ser["p"]
    start = bisect.bisect_right(times, t0)
    end_t = t0 + timedelta(days=HORIZON_DAYS)
    target = p0 * (1 + pct / 100.0)
    seen = False
    for j in range(start, len(times)):
        if times[j] > end_t:
            break
        seen = True
        if prices[j] >= target:
            return True
    return False if seen else None


def section_edge(audit: Audit):
    base = {"CALL": [0, 0], "PUT": [0, 0], "UNK": [0, 0]}       # [برد، تعداد]
    sig = {"CALL": [0, 0], "PUT": [0, 0]}
    skipped = Counter()
    for name, path in DBS:
        conn = open_db_or_report(audit, name, path)
        if conn is None:
            continue
        try:
            cols = table_columns(conn, "options")
            scols = table_columns(conn, "signal_history")
            if not {"time", "symbol", "option_price"} <= cols:
                audit.out(f"   {name}: جدول options ناقص است")
                continue
            if "price_fresh" not in cols:
                audit.out(f"   {name}: ستون price_fresh نیست؛ آزمون ممکن نیست")
                continue
            series = build_series(conn, cols)
            # نرخ پایه: اولین نقطه‌ی تازه‌ی هر قرارداد در هر روز
            for key, ser in series.items():
                seen_days = set()
                for i, t0 in enumerate(ser["t"]):
                    day = t0.date()
                    if day in seen_days:
                        continue
                    seen_days.add(day)
                    hit = reached(ser, t0, ser["p"][i], TARGET_PCT)
                    if hit is None:
                        continue
                    typ = ser["type"] if ser["type"] in ("CALL", "PUT") else "UNK"
                    base[typ][1] += 1
                    base[typ][0] += 1 if hit else 0
            # سیگنال‌ها: اولین ردیف هر پوزیشن
            need = {"id", "time", "signal_type", "option_price", "option_symbol", "position_id"}
            if not need <= scols:
                audit.out(f"   {name}: signal_history ناقص است؛ فقط نرخ پایه محاسبه شد")
                continue
            rows = q(conn,
                     "WITH b AS (SELECT position_id, MIN(id) AS f FROM signal_history WHERE position_id IS NOT NULL "
                     "AND signal_type IN ('BUY_CALL','BUY_PUT') GROUP BY position_id) "
                     "SELECT s.time, s.option_symbol, s.option_price, s.signal_type FROM b "
                     "JOIN signal_history s ON s.id=b.f WHERE s.time>=? ORDER BY s.time", (RELIABLE_START,))
            for t, osym, entry, stype in rows:
                dt = parse_ts(t)
                e = safe_float(entry)
                key = norm_sym(osym)
                if dt is None or e is None or e < MIN_OPTION_PRICE:
                    skipped["ورود نامعتبر"] += 1
                    continue
                ser = series.get(key)
                if ser is None:
                    skipped["قرارداد در داده‌ی تازه و نقدشونده نیست"] += 1
                    continue
                hit = reached(ser, dt, e, TARGET_PCT)
                if hit is None:
                    skipped["بعد از سیگنال داده‌ی تازه نیست"] += 1
                    continue
                typ = "CALL" if stype == "BUY_CALL" else "PUT"
                sig[typ][1] += 1
                sig[typ][0] += 1 if hit else 0
        finally:
            conn.close()

    k_sig = sig["CALL"][0] + sig["PUT"][0]
    n_sig = sig["CALL"][1] + sig["PUT"][1]
    k_base = sum(v[0] for v in base.values())
    n_base = sum(v[1] for v in base.values())
    p_base = safe_div(k_base, n_base)
    # نرخ مورد انتظار با ترکیب نوع سیگنال‌ها (کال/پوت) وزن‌دهی می‌شود
    exp_hits = 0.0
    for typ in ("CALL", "PUT"):
        n_t = sig[typ][1]
        r = safe_div(base[typ][0], base[typ][1], p_base)
        if n_t and r is not None:
            exp_hits += n_t * r
    p_exp = safe_div(exp_hits, n_sig, p_base)

    audit.out(f"معیار: رسیدن قیمت قرارداد به +{TARGET_PCT:.0f}٪ در {HORIZON_DAYS} روز بعد از ورود "
              f"(فقط قیمت‌های تازه و نقدشونده، از {RELIABLE_START})")
    lo_b, hi_b = wilson(k_base, n_base)
    audit.out(f"نرخ پایه‌ی انتخاب تصادفی: {k_base} از {n_base} ({fmt_pct(p_base)}) | "
              f"فاصله‌ی ۹۵٪: {fmt_pct(lo_b)} تا {fmt_pct(hi_b)}")
    for typ in ("CALL", "PUT"):
        r = safe_div(base[typ][0], base[typ][1])
        audit.out(f"   پایه‌ی {typ}: {base[typ][0]} از {base[typ][1]} ({fmt_pct(r)})")
    lo_s, hi_s = wilson(k_sig, n_sig)
    p_obs = safe_div(k_sig, n_sig)
    audit.out(f"سیگنال‌های ربات (هر پوزیشن یک بار): {k_sig} از {n_sig} ({fmt_pct(p_obs)}) | "
              f"فاصله‌ی ۹۵٪: {fmt_pct(lo_s)} تا {fmt_pct(hi_s)}")
    audit.out(f"نرخ مورد انتظار با همین ترکیب کال/پوت اگر سیگنال‌ها تصادفی بودند: {fmt_pct(p_exp)}")
    for reason, count in skipped.items():
        audit.out(f"   سیگنال کنار گذاشته‌شده — {reason}: {count}")

    verdict = "داده‌ی کافی برای آزمون نیست"
    p_hi = p_lo = None
    if n_sig > 0 and p_exp is not None:
        p_hi = binom_sf(k_sig, n_sig, p_exp)
        p_lo = binom_cdf(k_sig, n_sig, p_exp)
        audit.out(f"احتمال دیدن این تعداد برد یا بیشتر، در حالت تصادفی بودن: {p_hi:.3f}")
        if n_sig < 10:
            verdict = "نمونه آن‌قدر کم است که هیچ ادعایی (برتری یا ضعف) ممکن نیست"
        elif p_hi is not None and p_hi < 0.05 and p_obs is not None and p_obs > p_exp:
            verdict = "شواهد اولیه‌ی برتری نسبت به تصادف؛ با نمونه‌ی بیشتر باید تأیید شود"
        elif p_lo is not None and p_lo < 0.05:
            verdict = "سیگنال‌ها بدتر از انتخاب تصادفی بوده‌اند"
        else:
            verdict = "تفاوت معنی‌داری با انتخاب تصادفی دیده نمی‌شود"
    need_n = required_n(p_exp)
    audit.out(f"نتیجه: {verdict}")
    if need_n:
        audit.out(f"برای تشخیص برتری {UPLIFT_TO_DETECT * 100:.0f} واحد درصد نسبت به نرخ {fmt_pct(p_exp)} "
                  f"حدود {need_n} پوزیشن مستقل لازم است (الان {n_sig}).")
    audit.facts["edge"] = {"n": n_sig, "k": k_sig, "p_obs": p_obs, "p_exp": p_exp, "p_hi": p_hi,
                           "verdict": verdict, "need_n": need_n}
    for key, value in (("n_signals", n_sig), ("k_signals", k_sig), ("p_observed", p_obs),
                       ("p_expected", p_exp), ("p_value_upper", p_hi), ("required_n", need_n)):
        audit.record("edge", key, value)


# ----------------------------------------------------------------------------
# بخش ۵: رانش قوانین ثبت‌شده
# ----------------------------------------------------------------------------
def section_drift(audit: Audit):
    weekly = defaultdict(lambda: {"t": [], "s": []})
    for name, path in DBS:
        conn = open_db_or_report(audit, name, path)
        if conn is None:
            continue
        try:
            cols = table_columns(conn, "signal_history")
            need = {"id", "time", "signal_type", "option_price", "position_id", "target1", "stop_loss"}
            if not need <= cols:
                audit.out(f"   {name}: ستون target1 یا stop_loss نیست")
                continue
            rows = q(conn,
                     "WITH b AS (SELECT position_id, MIN(id) AS f FROM signal_history WHERE position_id IS NOT NULL "
                     "AND signal_type IN ('BUY_CALL','BUY_PUT') GROUP BY position_id) "
                     "SELECT s.time, s.option_price, s.target1, s.stop_loss FROM b "
                     "JOIN signal_history s ON s.id=b.f WHERE s.time>=?", (HISTORY_START,))
            for t, entry, t1, stop in rows:
                dt = parse_ts(t)
                e = safe_float(entry)
                if dt is None or e is None or e < MIN_OPTION_PRICE:
                    continue
                iso = dt.isocalendar()
                label = f"{iso[0]}-W{iso[1]:02d}"
                t1v = safe_div(t1, e)
                sv = safe_div(stop, e)
                if t1v is not None:
                    weekly[label]["t"].append((t1v - 1) * 100)
                if sv is not None:
                    weekly[label]["s"].append((sv - 1) * 100)
        finally:
            conn.close()
    if not weekly:
        audit.out("داده‌ای برای هدف و حد ضرر ثبت‌شده پیدا نشد")
        return
    audit.out("میانه‌ی فاصله‌ی هدف اول و حد ضرر ثبت‌شده در ربات، به تفکیک هفته (درصد نسبت به ورود):")
    audit.out(f"   {'هفته':<10}{'تعداد':>7}{'هدف اول':>10}{'حد ضرر':>10}")
    t_meds = []
    for label in sorted(weekly):
        ts, ss = weekly[label]["t"], weekly[label]["s"]
        t_med = statistics.median(ts) if ts else None
        s_med = statistics.median(ss) if ss else None
        if t_med is not None:
            t_meds.append(t_med)
        audit.out(f"   {label:<10}{max(len(ts), len(ss)):>7}"
                  f"{('؟' if t_med is None else f'{t_med:+.0f}'):>10}{('؟' if s_med is None else f'{s_med:+.0f}'):>10}")
    drift = None
    if len(t_meds) >= 2 and min(abs(x) for x in t_meds) > 0:
        drift = max(abs(x) for x in t_meds) / min(abs(x) for x in t_meds)
    audit.facts["drift_ratio"] = drift
    if drift is not None:
        audit.record("drift", "target_ratio_max_over_min", round(drift, 2))
        audit.out(f"نسبت بیشترین به کمترین میانه‌ی هدف اول بین هفته‌ها: {drift:.2f}"
                  + (" — قانون هدف بین هفته‌ها تغییر کرده" if drift > 1.3 else " — قانون هدف ثابت مانده"))
    audit.out("توجه: این فقط پارامترهای ثبت‌شده در دیتابیس را نشان می‌دهد؛ تغییرهای دیگر کد را نمی‌بیند.")


# ----------------------------------------------------------------------------
# بخش ۶: جمع‌بندی
# ----------------------------------------------------------------------------
def section_summary(audit: Audit):
    f = audit.facts
    audit.out("بر پایه‌ی اعداد همین اجرا:")
    ver = f.get("verifiable", {})
    if ver:
        shares = [v for v in ver.values() if v is not None]
        if shares:
            audit.out(f"۱. بنیان داده: فقط {fmt_pct(statistics.mean(shares))} از ردیف‌های options از {HISTORY_START} "
                      f"قابل راستی‌آزمایی است (میانگین {len(shares)} نماد بررسی‌شده). "
                      f"بقیه را نمی‌شود برای آزمون سیگنال‌ها به کار برد.")
    if f.get("partial_days"):
        audit.out(f"۲. روزهای ناقص در دوره‌ی معتبر: {', '.join(f['partial_days'][:8])}"
                  + (" ..." if len(f["partial_days"]) > 8 else ""))
    if f.get("noisy_days"):
        audit.out(f"۳. روزهای پرخطای سرور بورس/شبکه: {', '.join(f['noisy_days'][:8])}")
    led = f.get("ledger", {})
    if led:
        audit.out(f"۴. دفتر معاملات: {led.get('pos', 0)} پوزیشن، {led.get('rows', 0)} ردیف؛ ورود نامعتبر "
                  f"{led.get('bad_entry', 0)}، ناهم‌خوانی ورود {led.get('spread', 0)}، "
                  f"بیش از {HOLD_LIMIT_DAYS} روز باز: {f.get('overdue', 0)}.")
    edge = f.get("edge")
    if edge:
        audit.out(f"۵. آزمون برتری: {edge['k']} از {edge['n']} سیگنال به +{TARGET_PCT:.0f}٪ رسیده؛ "
                  f"{edge['verdict']}.")
        if edge.get("need_n"):
            audit.out(f"   برای تشخیص برتری {UPLIFT_TO_DETECT * 100:.0f} واحد درصد حدود {edge['need_n']} پوزیشن مستقل "
                      f"لازم است؛ الان {edge['n']} داریم.")
    if f.get("drift_ratio") is not None:
        audit.out(f"۶. رانش قوانین ثبت‌شده: نسبت هدف اول بیشترین به کمترین هفته = {f['drift_ratio']:.2f}.")
    if audit.failures:
        audit.out(f"⚠️ بخش‌های ناموفق در این اجرا: {', '.join(audit.failures)}")
    audit.out("این گزارش دلیل‌ها را اندازه می‌گیرد؛ تصمیم درباره‌ی ادامه‌ی پروژه با شماست.")


# ----------------------------------------------------------------------------
# اجرا
# ----------------------------------------------------------------------------
def write_report(audit: Audit, out_dir: Path):
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    try:
        (out_dir / f"project_audit_{stamp}.txt").write_text("\n".join(audit.lines), encoding="utf-8")
    except OSError as exc:
        log.error("نوشتن گزارش متنی ناموفق: %s", exc)
    try:
        with contextlib.closing(sqlite3.connect(str(out_dir / "audit.db"), timeout=5)) as c:
            c.execute("CREATE TABLE IF NOT EXISTS audit_results("
                      "run_ts TEXT, version TEXT, section TEXT, key TEXT, value TEXT)")
            run_ts = audit.run_id
            c.executemany("INSERT INTO audit_results(run_ts, version, section, key, value) VALUES (?,?,?,?,?)",
                          [(run_ts, VERSION, s, k, v) for s, k, v in audit.results])
            c.commit()
    except sqlite3.Error as exc:
        log.error("ذخیره‌ی نتایج در audit.db ناموفق: %s", exc)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    out_dir = setup_logging()
    audit = Audit()
    log.info("شروع ممیزی نسخه %s", VERSION)
    audit.out(f"ممیزی پروژه | نسخه {VERSION} | {datetime.now():%Y-%m-%d %H:%M} | "
              f"داده‌ی قابل اعتماد از {RELIABLE_START}")
    try:
        audit.run_section("۱. بنیان داده", section_data)
        audit.run_section("۲. لاگ‌ها و خطای سرور", section_logs)
        audit.run_section("۳. دفتر معاملات", section_ledger)
        audit.run_section("۴. آیا سیگنال‌ها از انتخاب تصادفی بهترند؟", section_edge)
        audit.run_section("۵. رانش قوانین ثبت‌شده", section_drift)
        audit.run_section("۶. جمع‌بندی", section_summary)
    finally:
        write_report(audit, out_dir)
        log.info("پایان ممیزی؛ بخش‌های ناموفق: %s", audit.failures or "ندارد")
    audit.out("")
    audit.out(f"گزارش در پوشه‌ی {out_dir} ذخیره شد.")
    return 2 if audit.failures else 0


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        print("متوقف شد (Ctrl+C).")
        code = 130
    except Exception as exc:  # noqa: BLE001 - آخرین خط دفاعی
        try:
            log.error("خطای پیش‌بینی‌نشده: %s\n%s", exc, traceback.format_exc())
        except Exception:  # noqa: BLE001
            pass
        print(f"خطای پیش‌بینی‌نشده: {type(exc).__name__}: {exc}")
        code = 1
    sys.exit(code)