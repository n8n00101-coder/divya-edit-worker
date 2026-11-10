import asyncio, json, edge_tts, subprocess
LINES = [
 "Did your phone just vibrate?",
 "You check it, and there's nothing there.",
 "Scientists call this, phantom vibration.",
 "In one study, eighty nine percent of students felt it.",
 "Your brain is so trained to expect alerts, it turns a tiny itch into a notification.",
 "Because we check our phones about ninety six times a day.",
 "And your brain learns what you repeat.",
 "So next time it buzzes, pause. Is it really there?",
]
VOICE = "en-US-AndrewNeural"
async def one(i, txt):
    c = edge_tts.Communicate(txt, VOICE, rate="+8%", boundary="WordBoundary")
    words = []
    with open(f"vo{i}.mp3", "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio": f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append([ch["text"], ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7])
    d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f"vo{i}.mp3"]))
    return {"text": txt, "words": words, "dur": d}
async def main():
    out = [await one(i, t) for i, t in enumerate(LINES)]
    json.dump(out, open("vo.json", "w"), indent=1)
    for o in out: print(round(o["dur"], 2), len(o["words"]), o["words"][:2])
asyncio.run(main())
