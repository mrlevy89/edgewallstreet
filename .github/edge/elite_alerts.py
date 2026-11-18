# Edge Elite call alerts and per-edition push.
#   diff ORIG_HTML NEW_HTML DATELINE  compare the calls in the picks slot; prepend changes to the call_alerts slot
#                                     of NEW_HTML (built from ORIG's log so the writer cannot alter it); save /tmp/alerts.json
#   notify DATELINE                   push "edition is live" to all push subscribers, then Elite call alerts to verified
#                                     Elite members by account id. Never fails the job; prints what happened.
import html, json, os, re, sys, urllib.request

NFA = "Educational, not financial advice."
APP_ID = "ba216a8f-f731-40cb-a743-0ab1a836799a"
SITE = "https://www.edgewallstreet.com/"
SB_RPC = "https://rtohcbtfwaukdtteswgz.supabase.co/rest/v1/rpc/"
SB_KEY = "sb_publishable_kZGErelCvaZNgaNw3wVj6g_HX_AQBvp"
MOVE = 1.0          # conviction change (points out of 10) that counts as an alert
MAX_PUSHES = 4      # per edition, so Elite members are not flooded
KEEP_ROWS = 30
ALERTS_JSON = "/tmp/alerts.json"


def slot(s, name):
    m = re.search(r'<div class="premium[^"]*" data-slot="%s"(?: data-tier="(?:pro|elite)")?>(.*?)<!-- /premium -->' % name, s, re.S)
    return m.group(1) if m else None


def calls(picks):
    out = {}
    for part in (picks or "").split('<div class="card-top">')[1:]:
        t = re.search(r'<span class="tick">(.*?)</span>', part)
        b = re.search(r'<span class="badge[^"]*">(.*?)</span>', part)
        c = re.search(r'<span class="conv-num">([\d.]+)/10</span>', part)
        if t and b and c:
            out[html.unescape(t.group(1)).strip()] = (html.unescape(b.group(1)).strip(), float(c.group(1)))
    return out


def diff(orig_path, new_path, dateline):
    o = open(orig_path, encoding="utf-8").read()
    n = open(new_path, encoding="utf-8").read()
    before, after = calls(slot(o, "picks")), calls(slot(n, "picks"))
    changes, new_calls = [], []
    for tick, (badge, conv) in after.items():
        if tick not in before:
            new_calls.append((tick, badge, conv))
            continue
        b0, c0 = before[tick]
        if badge != b0:
            changes.append((tick, f"{tick} call changed: {b0} to {badge}, conviction {conv:.1f}/10. {NFA}"))
        elif abs(conv - c0) >= MOVE:
            word = "up" if conv > c0 else "down"
            changes.append((tick, f"{tick} conviction {word}, {c0:.1f} to {conv:.1f}/10 ({badge}). {NFA}"))
    rows = [(t, msg) for t, msg in changes]
    rows += [(t, f"New call: {t}, {b}, conviction {c:.1f}/10. {NFA}") for t, b, c in new_calls]

    log = slot(o, "call_alerts") or ""
    old_rows = re.findall(r'<div class="alert-row">.*?</div></div>', log, re.S)
    when = html.escape(dateline.replace(" · ", ", ", 1).replace(" · ", ", "))
    fresh = []
    for t, msg in rows:
        body = html.escape(msg[: -len(NFA)].strip())
        fresh.append(f'<div class="alert-row"><div class="alert-when">{when}</div><div class="alert-what">{body} <span class="alert-nfa">{NFA}</span></div></div>')
    block = ""
    allrows = (fresh + old_rows)[:KEEP_ROWS]
    if allrows:
        block = '\n<div class="card">\n' + "\n".join(allrows) + "\n</div>\n"
    n, hits = re.subn(r'(<div class="premium[^"]*" data-slot="call_alerts" data-tier="elite">)(.*?)(<!-- /premium -->)', lambda m: m.group(1) + block + m.group(3), n, count=1, flags=re.S)
    if hits != 1:
        sys.exit("call_alerts slot not found")
    if block.count("<div") != block.count("</div>"):
        sys.exit("alert log unbalanced")
    open(new_path, "w", encoding="utf-8").write(n)

    pushes = [msg for _, msg in changes]
    if new_calls:
        names = ", ".join(f"{t} ({b}, {c:.1f}/10)" for t, b, c in new_calls[:4])
        pushes.append(f"New calls: {names}. {NFA}")
    json.dump({"pushes": pushes[:MAX_PUSHES], "count": len(rows)}, open(ALERTS_JSON, "w"))
    print(f"calls before {len(before)}, after {len(after)}; {len(rows)} alert(s); {min(len(pushes), MAX_PUSHES)} push(es) queued")


def post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "null")


def notify(dateline):
    key = os.environ.get("ONESIGNAL_REST_API_KEY", "")
    if not key:
        print("ONESIGNAL_REST_API_KEY not set; no pushes sent")
        return
    auth = {"Authorization": "Key " + key}
    edition = dateline.split(" · ")[-1]
    hero = ""
    try:
        s = open("index.html", encoding="utf-8").read()
        m = re.search(r'class="signal-type"[^>]*>(.*?)</', s, re.S)
        hero = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""
    except OSError:
        pass
    body = f"{edition} brief is live." + (f" {hero}." if hero and not hero.endswith(".") else (f" {hero}" if hero else ""))
    try:
        r = post("https://api.onesignal.com/notifications?c=push", {
            "app_id": APP_ID, "target_channel": "push",
            "included_segments": [os.environ.get("ONESIGNAL_SEGMENT") or "Subscribed Users"],
            "headings": {"en": "The Wall Street Edge"}, "contents": {"en": body}, "url": SITE,
        }, auth)
        print("edition push:", r)
    except Exception as e:  # never fail the publish over a push
        print("edition push failed:", e)

    try:
        alerts = json.load(open(ALERTS_JSON)).get("pushes", [])
    except (OSError, ValueError):
        alerts = []
    if not alerts:
        print("no Elite call alerts this edition")
        return
    try:
        ids = post(SB_RPC + "edge_elite_push_ids", {"p_token": os.environ.get("EDGE_PUBLISH_TOKEN", "")},
                   {"apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY}) or []
    except Exception as e:
        print("could not load Elite members:", e)
        return
    if not ids:
        print(f"{len(alerts)} Elite alert(s) ready, but there are no Elite members yet")
        return
    for msg in alerts:
        assert msg.endswith(NFA)
        try:
            r = post("https://api.onesignal.com/notifications?c=push", {
                "app_id": APP_ID, "target_channel": "push",
                "include_aliases": {"external_id": ids[:20000]},
                "headings": {"en": "Edge Elite call alert"}, "contents": {"en": msg}, "url": SITE + "#/alerts",
            }, auth)
            print("elite alert:", msg[:60], "->", r)
        except Exception as e:
            print("elite alert failed:", e)


if __name__ == "__main__":
    if sys.argv[1] == "diff":
        diff(sys.argv[2], sys.argv[3], sys.argv[4])
    elif sys.argv[1] == "notify":
        notify(sys.argv[2])
    else:
        sys.exit("usage: elite_alerts.py diff ORIG NEW DATELINE | notify DATELINE")
