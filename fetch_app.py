#!/usr/bin/env python3
"""Fetch the LIVE divya-app Worker bundle and extract the app files."""
import sys, re, json, base64
sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
import urllib.request
from dynamic_credentials import add_surrogate_to_request
ACCOUNT = "ba39b7fb8bae4e32999a8a77c8e04039"
API = "https://api.cloudflare.com/client/v4"
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args): raise RuntimeError("redirect refused")
req = urllib.request.Request(f"{API}/accounts/{ACCOUNT}/workers/scripts/divya-app/content/v2", method="GET")
req.add_header("Accept", "multipart/form-data")
add_surrogate_to_request(req, "custom.cloudflare", allowed_hosts=["api.cloudflare.com"])
with urllib.request.build_opener(NoRedirect()).open(req, timeout=120) as resp:
    raw = resp.read()
open(sys.argv[1], "wb").write(raw)
text = raw.decode("utf-8", "replace")
m = re.search(r'const F = (\{.*?\});\nconst cache', text, re.S)
if not m:
    print("NO BUNDLE MATCH"); sys.exit(1)
F = json.loads(m.group(1))
import os
os.makedirs(sys.argv[2], exist_ok=True)
for path, ent in F.items():
    if path == "/": continue
    name = path.lstrip("/")
    open(os.path.join(sys.argv[2], name), "wb").write(base64.b64decode(ent["b"]))
    print("extracted", name, len(base64.b64decode(ent["b"])))
