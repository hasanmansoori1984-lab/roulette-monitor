import json
import os
from datetime import datetime, timezone

# تنظیمات استراتژی
TRIGGER_ABSENCE = 6
BET_STEPS = [10, 15, 20, 40]

DOZENS = ("1", "2", "3")


def new_state():
    return {
        "spins_processed": 0,
        "dozens": {
            d: {
                "absence": 0,
                "active": False,
                "step": 0,
                "wins": 0,
                "losses": 0,
                "cycles_won": 0,
                "cycles_lost": 0,
                "profit": 0
            }
            for d in DOZENS
        }
    }


def load_state(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return new_state()


def save_state(state, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def dozen_of(number):
    if number == 0:
        return "0"
    if 1 <= number <= 12:
        return "1"
    if 13 <= number <= 24:
        return "2"
    if 25 <= number <= 36:
        return "3"
    raise ValueError("شماره باید بین صفر تا ۳۶ باشد")


def process_spin(number, state):
    hit = dozen_of(number)
    messages = []

    for d in DOZENS:
        item = state["dozens"][d]

        # چرخه فعال: نتیجه این دور، شرط قبلی را تعیین می‌کند.
        if item["active"]:
            stake = BET_STEPS[item["step"]]

            # برد: فقط وقتی همان دوجین بیاید.
            if hit == d:
                item["wins"] += 1
                item["cycles_won"] += 1
                item["profit"] += stake * 2

                messages.append(
                    f"دوجین {d}: برد با مبلغ {stake}؛ چرخه بسته شد."
                )

                item["active"] = False
                item["step"] = 0
                item["absence"] = 0

            else:
                # صفر هم طبق قانون مورد توافق، غیبت حساب می‌شود.
                item["losses"] += 1
                item["profit"] -= stake

                messages.append(
                    f"دوجین {d}: باخت شرط {stake}."
                )

                item["step"] += 1

                if item["step"] >= len(BET_STEPS):
                    item["cycles_lost"] += 1
                    item["active"] = False
                    item["step"] = 0
                    item["absence"] = 0

                    messages.append(
                        f"دوجین {d}: چهار شرط باخت؛ چرخه بسته شد."
                    )

        # شمارش غیبت برای چرخه بعدی
        if hit == d:
            item["absence"] = 0
        else:
            item["absence"] += 1

        # شروع چرخه جدید بعد از شش غیبت
        if not item["active"] and item["absence"] >= TRIGGER_ABSENCE:
            item["active"] = True
            item["step"] = 0

            messages.append(
                f"دوجین {d}: شش غیبت کامل شد؛ "
                f"شرط آزمایشی بعدی {BET_STEPS[0]}."
            )

    state["spins_processed"] += 1
    return messages


def report(state):
    lines = [
        "📊 گزارش آزمایشی استراتژی رولت",
        f"تعداد دورهای پردازش‌شده: {state['spins_processed']}",
        ""
    ]

    for d in DOZENS:
        item = state["dozens"][d]

        if item["active"]:
            next_bet = BET_STEPS[item["step"]]
            status = f"فعال؛ شرط بعدی: {next_bet}"
        else:
            status = "غیرفعال"

        lines.extend([
            f"دوجین {d}:",
            f"غیبت فعلی: {item['absence']}",
            f"وضعیت: {status}",
            f"برد شرط‌ها: {item['wins']}",
            f"باخت شرط‌ها: {item['losses']}",
            f"چرخه‌های برده‌شده: {item['cycles_won']}",
            f"چرخه‌های چهارباخت: {item['cycles_lost']}",
            f"سود/زیان فرضی: {item['profit']}",
            ""
        ])

    return "\n".join(lines)


if __name__ == "__main__":
    state_file = "strategy_state.json"
    state = load_state(state_file)

    print("موتور آزمایشی آماده است.")
    print("برای خروج، عدد -1 را وارد کن.")

    while True:
        try:
            raw = input("\nشماره نتیجه رولت (0 تا 36): ").strip()

            if raw == "-1":
                break

            number = int(raw)

            if not 0 <= number <= 36:
                print("عدد باید بین صفر تا ۳۶ باشد.")
                continue

            messages = process_spin(number, state)
            save_state(state, state_file)

            print("\n".join(messages) if messages else "نتیجه ثبت شد.")
            print()
            print(report(state))

        except ValueError:
            print("ورودی نامعتبر است.")

    print("\n" + report(state))
    print("اطلاعات در strategy_state.json ذخیره شد.")
