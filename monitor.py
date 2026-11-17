import json
import os
import requests

TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = str(os.environ["CHAT_ID"])
API = (
    "https://api-cs.casino.org/svc-evolution-game-events/api/autoroulette"
    "?page=0&size=100&sort=data.settledAt,desc&duration=6"
)
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
ALERTS = (5, 8)


def tg(method, **payload):
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        json=payload,
        timeout=20,
    )
    return r.json()


def send(text):
    tg("sendMessage", chat_id=CHAT_ID, text=text)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "last": None,
            "count": {"1": 0, "2": 0, "3": 0},
            "offset": 0,
            "error": False,
        }


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def fetch_spins():
    r = requests.get(API, headers=HEADERS, timeout=20)
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


def status_text(count):
    lines = [f"دازن {d} ({RANGES[d]}): {count[d]} غیبت" for d in "123"]
    return "📊 وضعیت فعلی\n" + "\n".join(lines)


def process(spins, state, notify):
    count = state["count"]
    for settled, n in spins:
        hit = dozen_of(n)
        for d in "123":
            if d == hit:
                count[d] = 0
            else:
                count[d] += 1
                if notify and count[d] in ALERTS:
                    send(
                        f"⚠️ دازن {d} ({RANGES[d]}) به {count[d]} غیبت رسید\n\n"
                        + status_text(count)
                    )
        state["last"] = settled


def handle_commands(state):
    res = tg("getUpdates", offset=state.get("offset", 0), timeout=0)
    for u in res.get("result", []):
        state["offset"] = u["update_id"] + 1
        msg = u.get("message") or {}
        text = (msg.get("text") or "").strip()
        if str(msg.get("chat", {}).get("id")) == CHAT_ID and text.startswith("/status"):
            send(status_text(state["count"]))


def main():
    state = load_state()
    try:
        spins = fetch_spins()
        if not spins:
            raise RuntimeError("پاسخ خالی بود")
    except Exception as e:
        if not state.get("error"):
            send(f"❌ خطا در دریافت نتایج:\n{str(e)[:300]}")
            state["error"] = True
        save_state(state)
        return

    if state.get("error"):
        send("✅ اتصال به منبع داده دوباره برقرار شد")
        state["error"] = False

    if state["last"] is None:
        process(spins, state, notify=False)
        send("🚀 ربات شروع به کار کرد\n\n" + status_text(state["count"]))
    else:
        new = [s for s in spins if s[0] > state["last"]]
        if new and len(new) == len(spins):
            send("⚠️ ممکن است چند چرخش از دست رفته باشد.")
        process(new, state, notify=True)

    try:
        handle_commands(state)
    except Exception:
        pass
    save_state(state)


main()
