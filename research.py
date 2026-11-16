"""RENDERER PIVOT (Phase 4): the RESEARCH RECORD.

Fact gate v1 validated that a source STRING existed on the scene —
the writer LLM invented the string ("Source: Nature 2022" under an
invented "up to 30%") and the gate stamped it. Fact gate v2 only
trusts sources that were actually RETRIEVED: this module fetches
real pages (Wikipedia's keyless API — the same keyless posture as
the stock pool) for the film's topic and returns a record of
{title, url, snippet}. anti_boring.fact_gate(research=record)
resolves every claim against THIS record; a free-text source the
writer made up matches nothing here and no longer counts, and
decorative source stamps may only print titles from the record.

The fetch is deliberately small and failure-honest: any error
returns what was gathered (possibly an empty record — the gate
then treats every claim as unresolvable: hedge or cut). Tests
inject a transport via set_transport().
"""

import json
import urllib.parse
import urllib.request

_UA = {"User-Agent": "JulieResearch/1.0 (documentary fact-check; "
                    "keyless Wikipedia API)"}
_transport = None


def set_transport(fn):
    """Test seam: fn(url) -> parsed JSON dict (or raise)."""
    global _transport
    _transport = fn


def _get_json(url, timeout=8):
    if _transport is not None:
        return _transport(url)
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _search(query, limit=4):
    """One Wikipedia search -> record entries with intro extracts."""
    qs = urllib.parse.urlencode({
        "action": "query", "generator": "search",
        "gsrsearch": query, "gsrlimit": str(limit),
        "prop": "extracts|info", "explaintext": "1", "exintro": "1",
        "inprop": "url", "format": "json",
    })
    data = _get_json("https://en.wikipedia.org/w/api.php?" + qs)
    pages = ((data or {}).get("query") or {}).get("pages") or {}
    out = []
    for pg in pages.values():
        title = str(pg.get("title") or "").strip()
        url = str(pg.get("fullurl") or "").strip()
        snippet = " ".join(str(pg.get("extract") or "").split())[:700]
        if title and url:
            out.append({"title": title, "url": url,
                        "snippet": snippet})
    return out


def build_research_record(topic, limit=6):
    """Fetch the research record for a film: the topic itself plus
    a statistics-flavoured pass (numbers live in those pages).
    Returns a list of {title, url, snippet} — possibly empty when
    the fetch fails; NEVER raises."""
    topic = " ".join(str(topic or "").split())
    if not topic:
        return []
    record, seen = [], set()
    for q in (topic, topic + " statistics"):
        try:
            for e in _search(q, limit=4):
                key = e["title"].lower()
                if key not in seen:
                    seen.add(key)
                    record.append(e)
        except Exception:
            pass
        if len(record) >= limit:
            break
    return record[:limit]
