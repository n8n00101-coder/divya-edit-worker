#!/bin/sh
# Deploy divya.js to Cloudflare keeping existing secrets/vars/KV bindings. Run with credentials provider cloudflare-divya.
A=ba39b7fb8bae4e32999a8a77c8e04039
cd "$(dirname "$0")"
curl -s -X PUT "https://api.cloudflare.com/client/v4/accounts/$A/workers/scripts/divya" \
  -F 'metadata={"main_module":"divya.js","compatibility_date":"2024-11-01","keep_bindings":["secret_text","plain_text","kv_namespace"]};type=application/json' \
  -F "divya.js=@divya.js;type=application/javascript+module" | python3 -c "import sys,json;r=json.load(sys.stdin);print('success',r['success'],r.get('errors'))"
