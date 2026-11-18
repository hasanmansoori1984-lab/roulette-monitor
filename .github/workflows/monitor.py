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
ALERTS = (7,)
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


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
        s.setdefault("last", None)
        s.setdefault("count", {"1": 0, "2": 0, "3": 0})
        s.setdefault("offset", 0)
        s.setdefault("error", False)
        return s
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


def status_text(state):
    lines = [
        f"دازن {d} ({RANGES[d]}): {state['count'][d]} غیبت" for d in "123"
    ]
    text = "📊 وضعیت فعلی\n" + "\n".join(lines)
    if state["last"]:
        text += f"\n\nآخرین چرخش: {fmt_age(age_seconds(state['last']))} پیش"
    return text


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
                        f"⚠️ دازن {d} ({RANGES[d]}) به {count[d]} غیبت رسید\n"
                        f"عدد آخر: {n}\n"
                        f"⏱ {fmt_age(age_seconds(settled))} از پایان چرخش گذشته\n\n"
                        + status_text(state)
                    )
        state["last"] = settled


def handle_commands(state):
    res = tg("getUpdates", offset=state.get("offset", 0), timeout=0)
    for u in res.get("result", []):
        state["offset"] = u["update_id"] + 1
        msg = u.get("message") or {}
        text = (msg.get("text") or "").strip()
        if str(msg.get("chat", {}).get("id")) == CHAT_ID and text.startswith("/status"):
            send(status_text(state))


def main():
    start = time.time()
    last_commit = time.time()
    state = load_state()
    fails = 0

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

        if time.time() - last_commit > COMMIT_EVERY:
            commit_state(state)
            last_commit = time.time()

        time.sleep(POLL_SECONDS)

    commit_state(state)


main()
