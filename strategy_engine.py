import json
import os

TRIGGER_ABSENCE = 6
BET_STEPS = [10, 15, 20, 40]
DOZENS = ("1", "2", "3")

STATE_FILE = "strategy_state.json"


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


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    return new_state()


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
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

    raise ValueError("عدد باید بین صفر تا ۳۶ باشد")


def process_spin(number, state):

    hit = dozen_of(number)
    messages = []

    for d in DOZENS:

        item = state["dozens"][d]

        # بررسی شرط فعال
        if item["active"]:

            stake = BET_STEPS[item["step"]]

            # حالت اول: برد
            if hit == d:

                item["wins"] += 1
                item["cycles_won"] += 1

                # پرداخت خالص برد دوجین
                item["profit"] += stake * 2

                messages.append(
                    f"✅ دوجین {d}: برد با شرط {stake}"
                )

                messages.append(
                    f"چرخه دوجین {d} بسته شد."
                )

                item["active"] = False
                item["step"] = 0
                item["absence"] = 0

            # حالت دوم: صفر
            elif hit == "0":

                messages.append(
                    f"🟡 دوجین {d}: صفر آمد؛ "
                    "غیبت حساب شد، شرط باخت محسوب نشد."
                )

                # مرحله شرط تغییر نمی‌کند.

            # حالت سوم: باخت
            else:

                item["losses"] += 1
                item["profit"] -= stake

                messages.append(
                    f"❌ دوجین {d}: باخت شرط {stake}"
                )

                item["step"] += 1

                # چهارمین باخت
                if item["step"] >= len(BET_STEPS):

                    item["cycles_lost"] += 1

                    messages.append(
                        f"⛔ دوجین {d}: چهار باخت متوالی؛ "
                        "چرخه بسته شد."
                    )

                    item["active"] = False
                    item["step"] = 0
                    item["absence"] = 0

        # شمارش غیبت
        if hit == d:
            item["absence"] = 0
        else:
            item["absence"] += 1

        # شروع چرخه جدید پس از شش غیبت
        if (
            not item["active"]
            and item["absence"] >= TRIGGER_ABSENCE
        ):

            item["active"] = True
            item["step"] = 0

            messages.append(
                f"🚀 دوجین {d}: شش غیبت کامل شد. "
                f"شرط آزمایشی بعدی: {BET_STEPS[0]}"
            )

    state["spins_processed"] += 1

    return messages


def report(state):

    lines = [
        "📊 گزارش آزمایشی استراتژی رولت",
        f"تعداد دورهای ثبت‌شده: {state['spins_processed']}",
        "--------------------------------"
    ]

    for d in DOZENS:

        item = state["dozens"][d]

        if item["active"]:
            status = (
                f"فعال | شرط بعدی: "
                f"{BET_STEPS[item['step']]}"
            )
        else:
            status = "غیرفعال"

        lines.extend([
            f"\n🎯 دوجین {d}",
            f"غیبت فعلی: {item['absence']}",
            f"وضعیت: {status}",
            f"برد شرط‌ها: {item['wins']}",
            f"باخت شرط‌ها: {item['losses']}",
            f"چرخه‌های برنده: {item['cycles_won']}",
            f"چرخه‌های چهارباخت: {item['cycles_lost']}",
            f"سود یا زیان فرضی: {item['profit']}",
        ])

    return "\n".join(lines)


def main():

    state = load_state()

    print("🤖 موتور آزمایشی استراتژی آماده است.")
    print("نتایج را از ۰ تا ۳۶ وارد کن.")
    print("برای خروج عدد -1 را وارد کن.")

    while True:

        raw = input("\nنتیجه رولت: ").strip()

        if raw == "-1":
            break

        try:
            number = int(raw)

            if not 0 <= number <= 36:
                print("عدد باید بین صفر تا ۳۶ باشد.")
                continue

        except ValueError:
            print("ورودی نامعتبر است.")
            continue

        messages = process_spin(number, state)

        save_state(state)

        if messages:
            for message in messages:
                print(message)
        else:
            print("نتیجه ثبت شد.")

        print("\n" + report(state))

    save_state(state)

    print("\nاطلاعات ذخیره شد.")
    print(report(state))


if __name__ == "__main__":
    main()
