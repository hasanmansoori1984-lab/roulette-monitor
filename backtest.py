import os
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
STAKES = {7: 0.10, 8: 0.15, 9: 0.20, 10: 0.40}


def send(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text[:4000]},
        timeout=20,
    )


def fetch(hours):
    spins = {}
    page = 0
    while page < 300:
        url = (
            f"{API_BASE}?page={page}&size=100"
            f"&sort=data.settledAt,desc&duration={hours}"
        )
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        items = r.json()
        if not items:
            break
        added = 0
        for it in items:
            d = it.get("data", {})
            try:
                sid = d["id"]
                if sid not in spins:
                    spins[sid] = (d["settledAt"], int(d["result"]["outcome"]["number"]))
                    added += 1
            except (KeyError, TypeError, ValueError):
                continue
        if added == 0:
            break
        page += 1
    return sorted(spins.values())


def dozen_of(n):
    return "0" if n == 0 else str((n - 1) // 12 + 1)


def simulate(spins):
    count = {"1": 0, "2": 0, "3": 0}
    openb = {}
    cyc = {}
    bets = []
    cycles = []
    for _, n in spins:
        hit = dozen_of(n)
        for d in "123":
            if d in openb:
                stake = openb.pop(d)
                pnl = round(2 * stake, 2) if d == hit else -stake
                bets.append((stake, pnl))
                cyc[d] = round(cyc.get(d, 0.0) + pnl, 2)
            if d == hit:
                count[d] = 0
            else:
                count[d] += 1
                if count[d] in STAKES and d not in openb:
                    openb[d] = STAKES[count[d]]
            if d in cyc and d not in openb:
                cycles.append(cyc.pop(d))
    return bets, cycles


def report(hours):
    spins = fetch(hours)
    if len(spins) < 50:
        return f"⚠️ برای {hours} ساعت داده‌ی کافی نیامد ({len(spins)} چرخش)."
    bets, cycles = simulate(spins)
    wins = sum(1 for c in cycles if c > 0)
    total = round(sum(c for c in cycles), 2)
    staked = round(sum(b[0] for b in bets), 2)
    peak = cum = worst = 0.0
    for c in cycles:
        cum += c
        peak = max(peak, cum)
        worst = min(worst, cum - peak)
    exp = round(len(cycles) * -0.0112, 2)
    return (
        f"🧪 شبیه‌سازی روی {hours} ساعت اخیر\n"
        f"چرخش‌های دریافتی: {len(spins)}\n"
        f"شرط‌ها: {len(bets)} | دوره‌ها: {len(cycles)}\n"
        f"دوره‌های با سود: {wins} | با باخت کامل: {len(cycles) - wins}\n"
        f"جمع پول گذاشته‌شده: {staked:.2f}€\n"
        f"سود/زیان کل: {total:+.2f}€\n"
        f"بدترین افت پشت‌سرهم: {worst:.2f}€\n"
        f"میانگین ریاضی برای این تعداد دوره: {exp:+.2f}€"
    )


for h in (24, 72):
    try:
        send(report(h))
    except Exception as e:
        send(f"❌ خطا در شبیه‌سازی {h} ساعت:\n{str(e)[:300]}")
