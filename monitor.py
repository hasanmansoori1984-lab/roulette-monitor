import json
import os
import subprocess
import time
from datetime import datetime, timezone

import requests

TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = str(os.environ["CHAT_ID"])
API_BASE = "https://api-cs.casino.org/svc-evolution-game-events/api/autoroulette"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Origin": "https://www.casino.org",
    "Referer": "https://www.casino.org/",
}
STATE_FILE = "state.json"
RANGES = {"1": "1-12", "2": "13-24", "3": "25-36"}

# آلارم فقط روی این غیبت‌ها
ALERTS = (5,)

# آمارگیری: بعد از رسیدن به این غیبت‌ها، STEPS چرخش بعدی رو دنبال کن
TRIGGERS = (5, 7)
STEPS = 4
MAX_STREAK = 30
REPORT_DAYS = 5

# گزارش طول غیبت: (از، تا). مثلاً (5, 9) یعنی بین غیبت‌هایی که به ۵ رسیدن، چندتاشون تا ۹ تموم شدن
BANDS = ((5, 9), (8, 12))

# سابقه: وقتی غیبت به TRIGGERS رسید، LOOKBACK چرخش قبل از شروع غیبت رو بررسی کن
LOOKBACK = 50
# (از، تا، علامت): تعداد اومدن دازن توی LOOKBACK چرخش قبل از شروع غیبت
#   16 یا بیشتر 🔴 | 14 و 15 ⚪ | 12 و 13 🟡 | 11 یا کمتر 🟢
LB_LEVELS = (
    (0, 11, "🟢"),
    (12, 13, "🟡"),
    (14, 15, "⚪"),
    (16, 99, "🔴"),
)
HISTORY_KEEP = 80

# قسمت‌های چرخ: ترتیب واقعی اعداد روی چرخ رولت اروپایی (از صفر)
WHEEL = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10,
    5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26,
]
# اندازه‌ی هر قسمت (جمعشون باید ۳۷ بشه): ۴ قسمت، ۳ تا ۹ تایی و ۱ تا ۱۰ تایی
SECTOR_SIZES = (9, 9, 9, 10)
# آلارم قسمت‌ها: وقتی این‌قدر چرخش پشت‌سرهم توپ توی اون قسمت نیفتاد
SECTOR_ALERTS = (10,)

assert sum(SECTOR_SIZES) == len(WHEEL) == 37
SECTORS = []
_i = 0
for _size in SECTOR_SIZES:
    SECTORS.append(WHEEL[_i:_i + _size])
    _i += _size
SECTOR_OF = {num: idx for idx, sec in enumerate(SECTORS) for num in sec}

POLL_SECONDS = 10
RUN_SECONDS = int(5.5 * 3600)
COMMIT_EVERY = 1200


def tg(method, **payload):
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        json=payload,
        timeout=20,
    )
    return r.json()


def send(text):
    try:
        tg("sendMessage", chat_id=CHAT_ID, text=text)
    except Exception:
        pass


def new_trial_stats():
    return {
        "n": 0,
        "wins": 0,
        "by_step": {str(i): 0 for i in range(1, STEPS + 1)},
    }


def new_stats():
    return {
        "spins": 0,
        "trials": {str(t): new_trial_stats() for t in TRIGGERS},
        "streak": {},
        "lookback50": {},
    }


def fresh_state():
    return {
        "last": None,
        "count": {"1": 0, "2": 0, "3": 0},
        "offset": 0,
        "error": False,
        "active": [],
        "history": [],
        "sectors": [0] * len(SECTORS),
        "stats": new_stats(),
        "next_report": None,
    }


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        return fresh_state()
    base = fresh_state()
    for k, v in base.items():
        s.setdefault(k, v)
    if len(s["sectors"]) != len(SECTORS):
        s["sectors"] = [0] * len(SECTORS)
    st = s["stats"]
    st.setdefault("spins", 0)
    st.setdefault("trials", {})
    st.setdefault("streak", {})
    st.setdefault("lookback50", {})
    for t in TRIGGERS:
        st["trials"].setdefault(str(t), new_trial_stats())
    return s


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def commit_state(state):
    save_state(state)
    try:
        subprocess.run(["git", "add", STATE_FILE], check=True)
        if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0:
            subprocess.run(["git", "commit", "-q", "-m", "state"], check=True)
            subprocess.run(["git", "push", "-q"], check=True)
    except Exception:
        pass


def fetch_spins(size):
    url = f"{API_BASE}?page=0&size={size}&sort=data.settledAt,desc&duration=6"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    spins = []
    for item in r.json():
        d = item.get("data", {})
        try:
            spins.append((d["settledAt"], int(d["result"]["outcome"]["number"])))
        except (KeyError, TypeError, ValueError):
            continue
    spins.sort()
    return spins


def dozen_of(n):
    return "0" if n == 0 else str((n - 1) // 12 + 1)


def age_seconds(iso):
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return max(0, int((datetime.now(timezone.utc) - t).total_seconds()))


def fmt_age(sec):
    if sec < 120:
        return f"{sec} ثانیه"
    return f"{sec // 60} دقیقه"


def pct(a, b):
    return f"{a / b * 100:.1f}%" if b else "—"


def lookback_hits(hist, d, t):
    """دازن d در LOOKBACK چرخش قبل از شروع غیبت t تایی چند بار اومده"""
    if len(hist) < t + LOOKBACK:
        return None
    window = hist[-(t + LOOKBACK):-t]
    return sum(1 for x in window if x == d)


def lb_level(lb):
    for lo, hi, emoji in LB_LEVELS:
        if lo <= lb <= hi:
            return f"{lo}-{hi}", emoji
    return None, "⚪"


def record_lookback(st, tr, won):
    lb = tr.get("lb")
    if lb is None or tr.get("lbw") != LOOKBACK:
        return
    key, _ = lb_level(lb)
    row = st["lookback50"].setdefault(str(tr["trigger"]), {}).setdefault(
        key, {"n": 0, "wins": 0}
    )
    row["n"] += 1
    if won:
        row["wins"] += 1


def sector_label(i):
    nums = " ".join(str(x) for x in SECTORS[i])
    return f"قسمت {i + 1} ({nums})"


def sectors_text(state):
    lines = ["🎡 غیبت قسمت‌های چرخ (چرخش پشت‌سرهم بدون اومدن توپ)"]
    for i in range(len(SECTORS)):
        lines.append(f"{sector_label(i)}: {state['sectors'][i]}")
    return "\n".join(lines)


def status_text(state):
    lines = [
        f"دازن {d} ({RANGES[d]}): {state['count'][d]} غیبت" for d in "123"
    ]
    text = "📊 وضعیت فعلی\n" + "\n".join(lines)
    if state["last"]:
        text += f"\n\nآخرین چرخش: {fmt_age(age_seconds(state['last']))} پیش"
    return text


def stats_text(state):
    st = state["stats"]
    base_win = (1 - (25 / 37) ** STEPS) * 100
    lines = [f"📈 آمار ({st['spins']} چرخش ثبت‌شده)"]

    for t in TRIGGERS:
        s = st["trials"][str(t)]
        n, w = s["n"], s["wins"]
        steps = " | ".join(
            f"{i}: {s['by_step'][str(i)]}" for i in range(1, STEPS + 1)
        )
        lines += [
            "",
            f"🎯 بعد از {t} غیبت ({STEPS} مرحله)",
            f"تعداد: {n} | برد: {w} ({pct(w, n)}) | باخت: {n - w} ({pct(n - w, n)})",
            f"برد در هر مرحله ← {steps}",
        ]

    lines += [
        "",
        f"برد تصادفی مورد انتظار در {STEPS} مرحله: {base_win:.1f}%",
    ]

    lines += [
        "",
        f"🔎 تعداد اومدن دازن در {LOOKBACK} چرخش قبل از شروع غیبت "
        f"(میانگین عادی: {LOOKBACK * 12 / 37:.1f})",
        f"(برد = اومدن توی {STEPS} مرحله‌ی بعد از رسیدن به غیبت)",
    ]
    for t in TRIGGERS:
        lines += ["", f"بعد از {t} غیبت:"]
        rows = st["lookback50"].get(str(t), {})
        for lo, hi, emoji in LB_LEVELS:
            r = rows.get(f"{lo}-{hi}", {"n": 0, "wins": 0})
            label = f"{lo}+" if hi >= LOOKBACK else f"{lo} تا {hi}"
            lines.append(
                f"{emoji} {label} بار: {r['n']} مورد | برد: {r['wins']} "
                f"({pct(r['wins'], r['n'])})"
            )

    # طول غیبت‌های تمام‌شده: غیبتی که با اومدن دازن تموم شده
    ends = {int(k): v["hit"] for k, v in st["streak"].items()}

    lines += ["", "📏 غیبت‌های تمام‌شده (طول = تعداد چرخش پشت‌سرهم بدون اومدن)"]
    for a, b in BANDS:
        total = sum(v for k, v in ends.items() if k >= a)
        inside = sum(v for k, v in ends.items() if a <= k <= b)
        beyond = total - inside
        rand = (1 - (25 / 37) ** (b - a + 1)) * 100
        lines += [
            "",
            f"غیبت‌های {a} به بالا: {total} بار",
            f"تموم شد بین {a} تا {b}: {inside} ({pct(inside, total)})",
            f"رفت بالاتر از {b}: {beyond} ({pct(beyond, total)})",
            f"تموم شدن بین {a} تا {b} در حالت تصادفی: {rand:.1f}%",
        ]

    start = min(a for a, _ in BANDS)
    total = sum(v for k, v in ends.items() if k >= start)
    lines += ["", f"📊 توزیع طول غیبت (از {start} به بالا، تعداد و درصد)"]
    for k in range(start, 21):
        c = ends.get(k, 0)
        lines.append(f"{k}: {c} ({pct(c, total)})")
    rest = sum(v for k, v in ends.items() if k > 20)
    lines.append(f"21+: {rest} ({pct(rest, total)})")
    return "\n".join(lines)


def process(spins, state, notify):
    count = state["count"]
    st = state["stats"]
    hist = state["history"]
    for settled, n in spins:
        hit = dozen_of(n)
        st["spins"] += 1
        hist.append(hit)
        if len(hist) > HISTORY_KEEP:
            del hist[:-HISTORY_KEEP]

        # قسمت‌های چرخ
        hit_sector = SECTOR_OF[n]
        alerted = []
        for i in range(len(SECTORS)):
            if i == hit_sector:
                state["sectors"][i] = 0
            else:
                state["sectors"][i] += 1
                if state["sectors"][i] in SECTOR_ALERTS:
                    alerted.append(i)
        if notify:
            for i in alerted:
                send(
                    f"🎡 {sector_label(i)}\n"
                    f"{state['sectors'][i]} چرخش پشت‌سرهم توپ توی این قسمت نیفتاد\n"
                    f"عدد آخر: {n}\n"
                    f"⏱ {fmt_age(age_seconds(settled))} از پایان چرخش گذشته\n\n"
                    + sectors_text(state)
                )

        # ۱) مرحله‌ی تست‌های در حال اجرا رو جلو ببر
        still = []
        for tr in state["active"]:
            tr["steps"] += 1
            s = st["trials"][str(tr["trigger"])]
            if tr["d"] == hit:
                s["n"] += 1
                s["wins"] += 1
                s["by_step"][str(tr["steps"])] += 1
                record_lookback(st, tr, True)
            elif tr["steps"] >= STEPS:
                s["n"] += 1
                record_lookback(st, tr, False)
            else:
                still.append(tr)
        state["active"] = still

        # ۲) آمار هر دازن + غیبت‌ها + آلارم
        for d in "123":
            k = count[d]
            if k >= 1:
                row = st["streak"].setdefault(
                    str(min(k, MAX_STREAK)), {"reached": 0, "hit": 0}
                )
                row["reached"] += 1
                if d == hit:
                    row["hit"] += 1

            if d == hit:
                count[d] = 0
            else:
                count[d] += 1
                lb = lookback_hits(hist, d, count[d])
                if count[d] in TRIGGERS:
                    state["active"].append(
                        {
                            "d": d,
                            "trigger": count[d],
                            "steps": 0,
                            "lb": lb,
                            "lbw": LOOKBACK,
                        }
                    )
                if notify and count[d] in ALERTS:
                    head = "⚠️"
                    lb_line = ""
                    if lb is not None:
                        _, emoji = lb_level(lb)
                        head = f"⚠️ {emoji}"
                        lb_line = (
                            f"📌 توی {LOOKBACK} چرخش قبل از شروع غیبت: "
                            f"{lb} بار اومده (میانگین عادی {LOOKBACK * 12 / 37:.1f})\n"
                        )
                    send(
                        f"{head} دازن {d} ({RANGES[d]}) به {count[d]} غیبت رسید\n"
                        f"عدد آخر: {n}\n"
                        + lb_line
                        + f"⏱ {fmt_age(age_seconds(settled))} از پایان چرخش گذشته\n\n"
                        + status_text(state)
                    )
        state["last"] = settled


def handle_commands(state):
    res = tg("getUpdates", offset=state.get("offset", 0), timeout=0)
    for u in res.get("result", []):
        state["offset"] = u["update_id"] + 1
        msg = u.get("message") or {}
        text = (msg.get("text") or "").strip()
        if str(msg.get("chat", {}).get("id")) != CHAT_ID:
            continue
        if text.startswith("/stats"):
            send(stats_text(state))
        elif text.startswith("/status"):
            send(status_text(state))
        elif text.startswith("/sectors"):
            send(sectors_text(state))


def main():
    start = time.time()
    last_commit = time.time()
    state = load_state()
    fails = 0

    if state["next_report"] is None:
        state["next_report"] = time.time() + REPORT_DAYS * 86400

    while time.time() - start < RUN_SECONDS:
        try:
            spins = fetch_spins(20 if state["last"] else 100)
            lost = False
            if state["last"] and spins and all(s[0] > state["last"] for s in spins):
                spins = fetch_spins(100)
                lost = all(s[0] > state["last"] for s in spins)
            if not spins:
                raise RuntimeError("پاسخ خالی بود")
        except Exception as e:
            fails += 1
            if fails >= 3 and not state["error"]:
                send(f"❌ خطا در دریافت نتایج:\n{str(e)[:300]}")
                state["error"] = True
            time.sleep(POLL_SECONDS)
            continue

        fails = 0
        if state["error"]:
            send("✅ اتصال به منبع داده دوباره برقرار شد")
            state["error"] = False

        if state["last"] is None:
            process(spins, state, notify=False)
            send("🚀 ربات شروع به کار کرد\n\n" + status_text(state))
        else:
            new = [s for s in spins if s[0] > state["last"]]
            if new:
                if lost:
                    send("⚠️ ممکن است چند چرخش از دست رفته باشد.")
                process(new, state, notify=True)

        try:
            handle_commands(state)
        except Exception:
            pass

        if time.time() >= state["next_report"]:
            send("📅 گزارش دوره‌ای\n\n" + stats_text(state))
            state["next_report"] = time.time() + REPORT_DAYS * 86400

        if time.time() - last_commit > COMMIT_EVERY:
            commit_state(state)
            last_commit = time.time()

        time.sleep(POLL_SECONDS)

    commit_state(state)


main()
