# Decides which edition (if any) this run should publish. Prints key=value lines for $GITHUB_OUTPUT.
import os, re
from datetime import datetime
from zoneinfo import ZoneInfo

now = datetime.now(ZoneInfo("America/Los_Angeles"))
wd, hr = now.isoweekday(), now.hour  # 1=Mon..7=Sun
force = os.environ.get("FORCE", "").lower() == "true"

ed = None
if wd <= 5 and hr < 9:
    ed = ("Pre-market", "Pre-market")
elif wd <= 5 and 9 <= hr <= 12:
    ed = ("Midday", "Midday")
elif wd <= 5 and 13 <= hr <= 17:
    ed = ("After the close", "After-close")
elif wd == 7 and hr >= 17:
    ed = ("Weekend catch-up", "Weekend catch-up")

def out(k, v):
    print(f"{k}={v}")

if ed is None:
    out("skip", "true")
    out("reason", f"off schedule ({now:%a %H:%M} PT)")
    raise SystemExit(0)

dateline = f"{now:%A} · {now:%b} {now.day} · {ed[0]}"
live = ""
m = re.search(r'<div class="date">(.*?)</div>', open("index.html", encoding="utf-8").read())
if m:
    live = m.group(1).replace("&middot;", "·")

out("dateline", dateline)
out("edition", ed[0])
out("label", ed[1])
out("date", f"{now:%Y-%m-%d}")
if live == dateline and not force:
    out("skip", "true")
    out("reason", "edition already live")
else:
    out("skip", "false")
