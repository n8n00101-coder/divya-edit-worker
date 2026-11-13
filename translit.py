"""translit.py — Indic -> Latin transliteration for captions
(v79.2, Ajju's caption rule, 2026-11-13).

Ajju: "Telugu captions ivvalsina avasaram ledhu — Romanized Telugu
lo ichina ok, English lo kuda ok." The burned-in Telugu-script
karaoke captions render broken glyphs/conjuncts in the caption
renderer (his screenshots prove it), and he does not want them
anyway. So when the narration language is Telugu (or Hindi — the
same shaping problem), captions default to a ROMANIZED
transliteration of the spoken line. Native script is used ONLY
when the user's prompt explicitly asks for it (spec_engine sets
cfg["caption_script"] = "native").

The transliteration is deterministic and character-level: Indic
scripts are phonetic, so a consonant carries an inherent "a", a
vowel sign (matra) replaces it, and the virama kills it. It aims
for readable Romanized Telugu/Hindi (the way the audience types
it), not scholarly ISO-15919: నిద్ర -> "nidra", శుభ్రం ->
"shubhram", नींद -> "neenda". Non-Indic characters (Latin words,
digits, punctuation) pass through untouched, so a mixed line keeps
its English words and numbers exactly as spoken.
"""

# ---------------- Telugu ----------------
_TE_VOWELS = {"అ": "a", "ఆ": "aa", "ఇ": "i", "ఈ": "ee", "ఉ": "u",
              "ఊ": "oo", "ఋ": "ru", "ఎ": "e", "ఏ": "ae", "ఐ": "ai",
              "ఒ": "o", "ఓ": "oo", "ఔ": "au"}
_TE_CONS = {"క": "k", "ఖ": "kh", "గ": "g", "ఘ": "gh", "ఙ": "ng",
            "చ": "ch", "ఛ": "chh", "జ": "j", "ఝ": "jh", "ఞ": "ny",
            "ట": "t", "ఠ": "th", "డ": "d", "ఢ": "dh", "ణ": "n",
            "త": "t", "థ": "th", "ద": "d", "ధ": "dh", "న": "n",
            "ప": "p", "ఫ": "ph", "బ": "b", "భ": "bh", "మ": "m",
            "య": "y", "ర": "r", "ల": "l", "వ": "v", "శ": "sh",
            "ష": "sh", "స": "s", "హ": "h", "ళ": "l", "ఱ": "r"}
_TE_MATRAS = {"ా": "aa", "ి": "i", "ీ": "ee", "ు": "u", "ూ": "oo",
              "ృ": "ru", "ె": "e", "ే": "ae", "ై": "ai", "ొ": "o",
              "ో": "oo", "ౌ": "au"}
_TE_VIRAMA = "్"
_TE_ANUSVARA = "ం"
_TE_SIGNS = {"ః": "h", "ఁ": "m"}
_TE_DIGITS = {chr(0x0C66 + i): str(i) for i in range(10)}

# ---------------- Devanagari (Hindi) ----------------
_HI_VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u",
              "ऊ": "oo", "ऋ": "ru", "ए": "ae", "ऐ": "ai", "ओ": "o",
              "औ": "au", "ऑ": "o", "ऍ": "ae"}
_HI_CONS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
            "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
            "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
            "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
            "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
            "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
            "ष": "sh", "स": "s", "ह": "h", "ळ": "l"}
_HI_MATRAS = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo",
              "ृ": "ru", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
              "ॉ": "o", "ॆ": "e"}
_HI_VIRAMA = "्"
_HI_ANUSVARA = "ं"
_HI_SIGNS = {"ः": "h", "ँ": "m"}
_HI_DIGITS = {chr(0x0966 + i): str(i) for i in range(10)}

_SCRIPT_MAPS = (
    (_TE_VOWELS, _TE_CONS, _TE_MATRAS, _TE_VIRAMA, _TE_ANUSVARA,
     _TE_SIGNS, _TE_DIGITS),
    (_HI_VOWELS, _HI_CONS, _HI_MATRAS, _HI_VIRAMA, _HI_ANUSVARA,
     _HI_SIGNS, _HI_DIGITS),
)
# char -> (kind, value, script_maps) for a one-pass scan
_LOOKUP = {}
for _maps in _SCRIPT_MAPS:
    _v, _c, _m, _vir, _anu, _sgn, _dig = _maps
    for _ch, _val in _v.items():
        _LOOKUP[_ch] = ("vowel", _val, _maps)
    for _ch, _val in _c.items():
        _LOOKUP[_ch] = ("cons", _val, _maps)
    for _ch, _val in _m.items():
        _LOOKUP[_ch] = ("matra", _val, _maps)
    _LOOKUP[_vir] = ("virama", "", _maps)
    _LOOKUP[_anu] = ("anusvara", "", _maps)
    for _ch, _val in _sgn.items():
        _LOOKUP[_ch] = ("sign", _val, _maps)
    for _ch, _val in _dig.items():
        _LOOKUP[_ch] = ("digit", _val, _maps)

_ZW = {"‌", "‍"}  # ZWNJ / ZWJ — dropped


def transliterate(text, lang="te"):
    """Romanize the Indic-script parts of `text`. Latin words,
    ASCII digits and punctuation pass through unchanged. `lang` is
    accepted for call-site clarity; the scan handles Telugu and
    Devanagari in one pass, whichever appears."""
    s = str(text or "")
    out = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch in _ZW:
            i += 1
            continue
        info = _LOOKUP.get(ch)
        if info is None:
            out.append(ch)
            i += 1
            continue
        kind, val, maps = info
        if kind == "cons":
            nxt = s[i + 1] if i + 1 < n else ""
            ninfo = _LOOKUP.get(nxt)
            if ninfo and ninfo[0] == "virama":
                out.append(val)          # inherent "a" killed
                i += 2
            elif ninfo and ninfo[0] == "matra":
                out.append(val + ninfo[1])
                i += 2
            else:
                out.append(val + "a")
                i += 1
        elif kind == "vowel":
            out.append(val)
            i += 1
        elif kind == "anusvara":
            # "n" before a consonant (neenda), "m" at a boundary
            # (shubhram) — the way the words are actually said.
            j = i + 1
            nxt = s[j] if j < n else ""
            ninfo = _LOOKUP.get(nxt)
            out.append("n" if (ninfo and ninfo[0] == "cons") else "m")
            i += 1
        elif kind in ("sign", "digit"):
            out.append(val)
            i += 1
        else:  # a stray matra/virama with no consonant before it
            i += 1
    return "".join(out)
