import os
import requests
from playwright.sync_api import sync_playwright

URL = "https://www.casino.org/casinoscores/auto-roulette/"
found = []


def on_response(resp):
    try:
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            found.append((resp.url, resp.text()[:400]))
    except Exception:
        pass


def send(text):
    token = os.environ["BOT_TOKEN"]
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": os.environ["CHAT_ID"], "text": text[:4000]},
        timeout=15,
    )


page_text = ""
error = ""
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("response", on_response)
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(8000)
        page_text = page.inner_text("body")[:800]
        browser.close()
except Exception as e:
    error = str(e)[:500]

send(f"گزارش کشف منبع\nتعداد پاسخ JSON: {len(found)}\nخطا: {error or 'ندارد'}")

keys = ("outcome", "number", "result", "spin", "round")
good = [f for f in found if any(k in f[1].lower() for k in keys)]
rest = [f for f in found if f not in good]

for url, body in good[:6]:
    send(f"JSON مشکوک به نتیجه:\n{url}\n\n{body}")

if rest:
    send("بقیه آدرس‌ها:\n" + "\n".join(u for u, _ in rest[:25]))

if page_text:
    send("متن صفحه:\n" + page_text)
