import os
import requests

token = os.environ["BOT_TOKEN"]
chat_id = os.environ["CHAT_ID"]

r = requests.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    json={"chat_id": chat_id, "text": "✅ ربات وصل شد"},
    timeout=15,
)
print(r.status_code, r.text)
r.raise_for_status()
