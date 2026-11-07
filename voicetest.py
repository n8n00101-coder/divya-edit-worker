import glob, os, time, torch, torchaudio as ta
torch.set_num_threads(os.cpu_count() or 4)
from chatterbox.tts import ChatterboxTTS
m = ChatterboxTTS.from_pretrained(device="cpu")
T = ("Why one cigarette is never enough? When someone smokes, nicotine reaches the brain in about ten seconds. "
     "And here is the scary part. The part of you that should say no, gets weaker.")
os.makedirs("out", exist_ok=True)
for ref in sorted(glob.glob("voices/refs/*.wav")):
    n = os.path.basename(ref)[:-4]; t = time.time()
    w = m.generate(T, audio_prompt_path=ref, exaggeration=0.55, cfg_weight=0.4, temperature=0.7)
    ta.save(f"out/{n}.wav", w, m.sr)
    print(n, "audio", round(w.shape[-1]/m.sr,1), "s, took", round(time.time()-t,1), "s", flush=True)
