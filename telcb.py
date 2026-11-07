import os, time, torch, torchaudio as ta
from pathlib import Path
from huggingface_hub import snapshot_download
from safetensors.torch import load_file
import chatterbox.mtl_tts as M
from chatterbox.models.t3 import T3
from chatterbox.models.t3.modules.t3_config import T3Config
from chatterbox.models.s3gen import S3Gen
from chatterbox.models.voice_encoder import VoiceEncoder
from chatterbox.models.tokenizers import MTLTokenizer
os.makedirs("out", exist_ok=True); torch.set_num_threads(os.cpu_count())
M.SUPPORTED_LANGUAGES["te"] = "Telugu"
d = Path(snapshot_download("shankarpandala/chatterbox-telugu"))
ve = VoiceEncoder(); ve.load_state_dict(torch.load(d/"ve.pt", map_location="cpu", weights_only=True)); ve.eval()
T3Config.is_multilingual = property(lambda s: s.text_tokens_dict_size != 704)
cfg = T3Config.multilingual(); cfg.text_tokens_dict_size = 2521
t3 = T3(cfg); sd = load_file(d/"t3_mtl_te.safetensors")
if "model" in sd: sd = sd["model"][0]
print(t3.load_state_dict(sd, strict=False)); t3.eval()
s3 = S3Gen(); s3.load_state_dict(torch.load(d/"s3gen.pt", map_location="cpu", weights_only=True)); s3.eval()
tok = MTLTokenizer(str(d/"grapheme_mtl_merged_expanded_v1.json"))
m = M.ChatterboxMultilingualTTS(t3, s3, ve, tok, "cpu")
REF = "voices/refs/S_006830_12s.wav"
TE = ["ఒక్క సిగరెట్ ఎప్పుడూ ఎందుకు సరిపోదు?",
      "ఎవరైనా సిగరెట్ తాగినప్పుడు, నికోటిన్ దాదాపు పది సెకన్లలో మెదడుకు చేరుతుంది.",
      "ఇంకా భయంకరమైన విషయం ఏంటంటే, వద్దు అని చెప్పాల్సిన మీలోని భాగం బలహీనపడుతుంది."]
parts=[]
for i,t in enumerate(TE):
    s=time.time(); w = m.generate(t, language_id="te", audio_prompt_path=REF, exaggeration=0.5, cfg_weight=0.5)
    parts += [w, torch.zeros(1, int(0.3*m.sr))]; print(i, round(w.shape[-1]/m.sr,1), "s in", round(time.time()-s,1), flush=True)
ta.save("out/te_cb.wav", torch.cat(parts, -1), m.sr)
