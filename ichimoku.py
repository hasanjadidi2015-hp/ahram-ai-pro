# -*- coding: utf-8 -*-
"""
================================================================
  ☁️  Ichimoku Kinko Hyo  —  نسخه‌ی ۳ (ابر ضخیم + پیچ/برگشت روند)
================================================================
  بهبودهای این نسخه:
    ✅ کیفیت ابر (STRONG/NORMAL/THIN) بر اساس ضخامت
    ✅ تشخیص «پیچ» ابرِ فعلی (برگشت روند)
    ✅ تشخیص «پیچ» ابرِ آینده (هشدار زودهنگام، ۲۶ دوره جلوتر)
    ✅ هشدار برگشت روند (reversal_warning)

  رابط (تغییر نکرده — با strategy.py سازگاره):
      Ichimoku(df).calculate()  →  "BULLISH" / "BEARISH" / "NEUTRAL"

  خروجی‌های اضافه (برای داشبورد/آینده):
      ich.cloud_quality   : STRONG / NORMAL / THIN
      ich.twist           : NONE / BULLISH_TWIST / BEARISH_TWIST  (ابر فعلی)
      ich.leading_twist   : NONE / BULLISH_TWIST / BEARISH_TWIST  (ابر آینده)
      ich.reversal_warning: True/False
      ich.strength        : ۰..۱۰۰
      ich.details         : دیکشنری جزئیات
================================================================
"""
import pandas as pd


class Ichimoku:

    def __init__(self, df):
        self.df = df.copy()
        self.strength = 50
        self.cloud_color = "FLAT"
        self.cloud_quality = "NORMAL"     # STRONG / NORMAL / THIN
        self.twist = "NONE"               # پیچ ابر فعلی
        self.leading_twist = "NONE"       # پیچ ابر آینده
        self.reversal_warning = False
        self.details = {}

    # ------------------------------------------------------------
    @staticmethod
    def _twist_of(now_green, prev_green):
        """تقاطع سبز/قرمز رو به نوع پیچ تبدیل می‌کنه."""
        if now_green and not prev_green:
            return "BULLISH_TWIST"
        if (not now_green) and prev_green:
            return "BEARISH_TWIST"
        return "NONE"

    def calculate(self):
        price = self.df["last_price"]

        # ---------- محاسبه‌ی خطوط ----------
        high9, low9 = price.rolling(9).max(), price.rolling(9).min()
        high26, low26 = price.rolling(26).max(), price.rolling(26).min()
        high52, low52 = price.rolling(52).max(), price.rolling(52).min()

        tenkan = (high9 + low9) / 2
        kijun = (high26 + low26) / 2
        # ابرِ فعلی (۲۶ دوره به جلو نمایش داده می‌شه)
        senkou_a = ((tenkan + kijun) / 2).shift(26)
        senkou_b = ((high52 + low52) / 2).shift(26)
        # ابرِ آینده (هشدار زودهنگام) — بدون شیفت
        leading_a = (tenkan + kijun) / 2
        leading_b = (high52 + low52) / 2

        self.df["tenkan"] = tenkan
        self.df["kijun"] = kijun
        self.df["senkou_a"] = senkou_a
        self.df["senkou_b"] = senkou_b

        last = self.df.iloc[-1]

        if pd.isna(last["senkou_a"]) or pd.isna(last["senkou_b"]):
            return "NEUTRAL"

        p = float(last["last_price"])
        sa = float(last["senkou_a"])
        sb = float(last["senkou_b"])
        tk = float(last["tenkan"])
        kj = float(last["kijun"])
        la = float(leading_a.iloc[-1])
        lb = float(leading_b.iloc[-1])

        # ---------- ویژگی‌های ابر ----------
        cloud_top = max(sa, sb)
        cloud_bottom = min(sa, sb)
        cloud_color = "GREEN" if sa > sb else ("RED" if sa < sb else "FLAT")
        thick_pct = ((cloud_top - cloud_bottom) / p * 100.0) if p > 0 else 0.0
        # کیفیت ابر بر اساس ضخامت نسبی
        if thick_pct >= 3.0:
            cloud_quality = "STRONG"
        elif thick_pct < 1.0:
            cloud_quality = "THIN"
        else:
            cloud_quality = "NORMAL"

        self.cloud_color = cloud_color
        self.cloud_quality = cloud_quality

        # ---------- تشخیص پیچ (برگشت روند) ----------
        # پیچِ ابرِ فعلی
        if len(self.df) >= 2:
            prev = self.df.iloc[-2]
            if pd.notna(prev["senkou_a"]) and pd.notna(prev["senkou_b"]):
                self.twist = self._twist_of(sa > sb, float(prev["senkou_a"]) > float(prev["senkou_b"]))
        # پیچِ ابرِ آینده (هشدار زودهنگام)
        if len(leading_a) >= 2 and pd.notna(leading_a.iloc[-2]) and pd.notna(leading_b.iloc[-2]):
            self.leading_twist = self._twist_of(la > lb, float(leading_a.iloc[-2]) > float(leading_b.iloc[-2]))

        # هشدار برگشت: ابر آینده در خلاف جهتِ ابر فعلی در حال پیچیدنه
        future_green = la > lb
        current_green = cloud_color == "GREEN"
        self.reversal_warning = (future_green != current_green)

        # ---------- تأیید چیکو ----------
        chikou_bull = chikou_bear = False
        if len(price) > 26:
            p26 = price.iloc[-27]
            if pd.notna(p26):
                chikou_bull = p > float(p26)
                chikou_bear = p < float(p26)

        above_kijun = p > kj
        below_kijun = p < kj

        # ---------- ذخیره‌ی جزئیات ----------
        self.details = {
            "price": round(p, 2),
            "tenkan": round(tk, 2),
            "kijun": round(kj, 2),
            "cloud_top": round(cloud_top, 2),
            "cloud_bottom": round(cloud_bottom, 2),
            "cloud_color": cloud_color,
            "cloud_quality": cloud_quality,
            "cloud_thick_pct": round(thick_pct, 2),
            "twist": self.twist,
            "leading_twist": self.leading_twist,
            "reversal_warning": self.reversal_warning,
            "above_cloud": p > cloud_top,
            "below_cloud": p < cloud_bottom,
            "tenkan_above_kijun": tk > kj,
            "above_kijun": above_kijun,
            "chikou_bull": chikou_bull,
            "chikou_bear": chikou_bear,
        }

        # ---------- امتیاز قدرت ----------
        score = 0
        if p > cloud_top:          score += 30
        elif p < cloud_bottom:     score -= 30
        if cloud_color == "GREEN": score += 15
        elif cloud_color == "RED": score -= 15
        if tk > kj:                score += 20
        elif tk < kj:              score -= 20
        if chikou_bull:            score += 20
        elif chikou_bear:          score -= 20
        if above_kijun:            score += 15
        elif below_kijun:          score -= 15

        # بونوس/جریمه‌ی کیفیت ابر: ابر ضخیم در جهت روند = تأیید قوی‌تر
        if cloud_quality == "STRONG":
            score += 5 if score > 0 else (-5 if score < 0 else 0)
        elif cloud_quality == "THIN":
            score -= 5 if score > 0 else (-5 if score < 0 else 0)

        # بونوس پیچ در جهت سیگنال
        if self.twist == "BULLISH_TWIST":      score += 5
        elif self.twist == "BEARISH_TWIST":    score -= 5

        self.strength = max(0, min(100, 50 + score))

        # ---------- تصمیم نهایی ----------
        # BULLISH: بالای ابر + ابر سبز + تنکان>کیجون + چیکو صعودی
        if (p > cloud_top and cloud_color == "GREEN"
                and tk > kj and chikou_bull):
            signal = "BULLISH"
        # BEARISH: زیر ابر + ابر قرمز + تنکان<کیجون + چیکو نزولی
        elif (p < cloud_bottom and cloud_color == "RED"
                and tk < kj and chikou_bear):
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        if signal == "NEUTRAL":
            self.strength = int(50 + (self.strength - 50) * 0.5)

        return signal


if __name__ == "__main__":
    import sqlite3
    import config

    conn = sqlite3.connect(config.DATABASE_NAME)
    df = pd.read_sql("SELECT last_price FROM prices ORDER BY id", conn)
    conn.close()

    ich = Ichimoku(df)
    signal = ich.calculate()
    print("=" * 55)
    print("ایچیموکو (نسخه‌ی ۳ — ابر ضخیم + پیچ)")
    print("=" * 55)
    print("سیگنال         :", signal)
    print("قدرت سیگنال    :", ich.strength, "/ 100")
    print("رنگ ابر        :", ich.cloud_color, "| کیفیت:", ich.cloud_quality)
    print("پیچ ابر فعلی   :", ich.twist)
    print("پیچ ابر آینده  :", ich.leading_twist)
    print("هشدار برگشت    :", "⚠️ بله" if ich.reversal_warning else "خیر")
    print("-" * 55)
    for k, v in ich.details.items():
        print(f"  {k:<20}: {v}")
    print("=" * 55)