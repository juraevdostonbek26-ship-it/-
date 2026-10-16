from datetime import date
import bot

CFG = bot.load(bot.CFG, {})

def test_due_clamped_to_month_end():
    assert bot.due_date({"id": "x", "day": 30}, 2026, 2) == date(2026, 2, 28)

def test_quarterly():
    p = {"id": "q", "freq": "quarterly", "day": 25, "month": 1}
    assert bot.due_date(p, 2026, 4) and not bot.due_date(p, 2026, 5)

def test_reminders_and_paid():
    st = {"paid": {}}
    r = bot.todays_reminders(CFG, st, date(2026, 11, 2))  # аренда 5-ноябр, 3 кун қолган
    assert any(p["id"] == "arenda" and left == 3 for p, d, left in r)
    st["paid"]["arenda:2026-11-05"] = "x"
    assert not any(p["id"] == "arenda" for p, d, left in bot.todays_reminders(CFG, st, date(2026, 11, 2)))

def test_year_rollover():
    assert bot.upcoming({"id": "a", "day": 5}, date(2026, 12, 20))[0] == date(2027, 1, 5)
