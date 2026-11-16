#!/usr/bin/env python3
"""Fetch the LIVE divya Worker script bytes via the Cloudflare API.
Read-only. Saves raw multipart response + extracted main module."""
import sys, re
sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
import urllib.request
from dynamic_credentials import add_surrogate_to_request

ACCOUNT = "ba39b7fb8bae4e32999a8a77c8e04039"
API = "https://api.cloudflare.com/client/v4"

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused")

def get_raw(url):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "multipart/form-data")
    add_surrogate_to_request(req, "custom.cloudflare", allowed_hosts=["api.cloudflare.com"])
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=120) as resp:
        return resp.read(), resp.headers.get("Content-Type", "")

raw, ctype = get_raw(f"{API}/accounts/{ACCOUNT}/workers/scripts/divya/content/v2")
open(sys.argv[1], "wb").write(raw)
print("raw bytes:", len(raw), "ctype:", ctype[:60])
text = raw.decode("utf-8", "replace")
m = re.search(r'name="divya\.js"[^\n]*\n(?:[^\n]*\n)*?\r?\n(.*)\r?\n--[0-9a-fA-F-]+--', text, re.S)
if m:
    open(sys.argv[2], "w", encoding="utf-8").write(m.group(1))
    print("extracted module bytes:", len(m.group(1)))
else:
    print("NO MODULE MATCH — inspect raw manually")
