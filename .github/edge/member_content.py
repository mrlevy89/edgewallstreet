# Member-only sections live in Supabase (public.member_content, RLS: paying members only), never in the public repo.
#   load     pull current member sections into the working index.html so the writer can edit them in place
#   publish  push every member section to Supabase, then strip them from index.html before commit (fails closed)
# A slot is everything between <div class="premium..." data-slot="NAME" [data-tier="elite"]> and <!-- /premium -->.
import json, os, re, sys, urllib.request

URL = "https://rtohcbtfwaukdtteswgz.supabase.co/rest/v1/rpc/"
KEY = "sb_publishable_kZGErelCvaZNgaNw3wVj6g_HX_AQBvp"  # public key; the publish token is what authorizes writes
SLOT = re.compile(r'(<div class="premium[^"]*" data-slot="([a-z_]+)"(?: data-tier="(pro|elite)")?>)(.*?)(<!-- /premium -->)', re.S)
REQUIRED = {"today": 500, "picks": 500}  # these must never publish empty


def rpc(fn, body):
    token = os.environ.get("EDGE_PUBLISH_TOKEN", "")
    if not token:
        sys.exit("EDGE_PUBLISH_TOKEN secret is not set")
    body["p_token"] = token
    req = urllib.request.Request(URL + fn, data=json.dumps(body).encode(), method="POST",
                                 headers={"apikey": KEY, "Authorization": "Bearer " + KEY,
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode() or "null")


def main():
    cmd = sys.argv[1]
    path = "index.html"
    s = open(path, encoding="utf-8").read()
    slots = SLOT.findall(s)
    if not any(m[1] == "today" for m in slots) or not any(m[1] == "picks" for m in slots):
        sys.exit("member slots missing from index.html")

    if cmd == "load":
        stored = rpc("edge_read_member_content", {}) or {}
        def fill(m):
            got = stored.get(m.group(2), {}).get("html", "")
            return m.group(1) + (got or m.group(4)) + m.group(5)
        s = SLOT.sub(fill, s)
        for name, minlen in REQUIRED.items():
            if len(stored.get(name, {}).get("html", "")) < minlen:
                print(f"warning: stored slot {name} is empty; writer will build it from scratch")
        open(path, "w", encoding="utf-8").write(s)
        print("loaded slots:", ", ".join(sorted(stored)))

    elif cmd == "publish":
        edition = sys.argv[2] if len(sys.argv) > 2 else None
        payload = {}
        for opening, name, tier, body, _ in slots:
            if body.count("<div") != body.count("</div>"):
                sys.exit(f"slot {name} has unbalanced divs")
            if len(body.strip()) < REQUIRED.get(name, 0):
                sys.exit(f"slot {name} is empty; refusing to publish")
            if body.strip():
                payload[name] = {"min_tier": tier or "pro", "html": body}
        n = rpc("edge_publish_member_content", {"p_slots": payload, "p_edition": edition})
        if n != len(payload):
            sys.exit(f"publish wrote {n} of {len(payload)} slots")
        s = SLOT.sub(lambda m: m.group(1) + "\n" + m.group(5), s)
        if any(m[3].strip() for m in SLOT.findall(s)):
            sys.exit("strip failed")
        open(path, "w", encoding="utf-8").write(s)
        print("published and stripped:", ", ".join(sorted(payload)))
    else:
        sys.exit("usage: member_content.py load|publish [edition]")


if __name__ == "__main__":
    main()
