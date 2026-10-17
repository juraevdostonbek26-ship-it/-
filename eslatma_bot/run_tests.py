"""Ҳамма тестни ишга туширади: python3 run_tests.py"""
import sys, traceback
import test_bot, test_e2e

bad = n = 0
for mod in (test_bot, test_e2e):
    for name in sorted(dir(mod)):
        if name.startswith("test_"):
            n += 1
            try:
                getattr(mod, name)()
                print("OK  ", mod.__name__, name)
            except Exception:
                bad += 1
                print("FAIL", mod.__name__, name)
                traceback.print_exc(limit=-4)
print(f"\nЖами: {n}, муваффақиятсиз: {bad}")
sys.exit(1 if bad else 0)
