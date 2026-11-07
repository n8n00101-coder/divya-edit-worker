import os, time, torch, torchaudio as ta
torch.set_num_threads(os.cpu_count() or 4)
os.makedirs("out", exist_ok=True)
REF = "voices/refs/S_006830.wav"
from chatterbox.tts import ChatterboxTTS
m = ChatterboxTTS.from_pretrained(device="cpu")
T = ("Why one cigarette is never enough? When someone smokes, nicotine reaches the brain in about ten seconds. "
     "And here is the scary part. The part of you that should say no, gets weaker.")
t=time.time(); w = m.generate(T, audio_prompt_path=REF, exaggeration=0.55, cfg_weight=0.4, temperature=0.7)
ta.save("out/en.wav", w, m.sr); print("en", round(w.shape[-1]/m.sr,1), round(time.time()-t,1), flush=True)
del m
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
mm = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
H = "एक सिगरेट कभी काफी क्यों नहीं होती? जब कोई सिगरेट पीता है, तो निकोटीन लगभग दस सेकंड में दिमाग तक पहुँच जाता है। और सबसे डरावनी बात, आपके अंदर का वो हिस्सा जो ना कहना चाहिए, कमज़ोर हो जाता है।"
t=time.time(); w = mm.generate(H, language_id="hi", audio_prompt_path=REF, exaggeration=0.55, cfg_weight=0.4, temperature=0.7)
ta.save("out/hi.wav", w, mm.sr); print("hi", round(w.shape[-1]/mm.sr,1), round(time.time()-t,1), flush=True)
