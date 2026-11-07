import os, time, torch, torchaudio as ta
torch.set_num_threads(os.cpu_count() or 4); os.makedirs("out", exist_ok=True)
SPK=os.environ["SPK"]; REF=f"voices/refs/young/{SPK}.wav"
from chatterbox.tts import ChatterboxTTS
m = ChatterboxTTS.from_pretrained(device="cpu")
T = ("Why one cigarette is never enough? When someone smokes, nicotine reaches the brain in about ten seconds. "
     "And here is the scary part. The part of you that should say no, gets weaker.")
t=time.time(); w = m.generate(T, audio_prompt_path=REF, exaggeration=0.55, cfg_weight=0.4, temperature=0.7)
ta.save(f"out/{SPK}.wav", w, m.sr); print(SPK, round(w.shape[-1]/m.sr,1), round(time.time()-t,1), flush=True)
