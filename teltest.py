import os, time, numpy as np, soundfile as sf, torch
from transformers import AutoModel
os.makedirs("out", exist_ok=True)
torch.set_num_threads(os.cpu_count())
m = AutoModel.from_pretrained("Aditya02/IndicF5", trust_remote_code=True)
RT = "Mary told me that she got to meet up with you while she was back in San Francisco. Dense clouds of smoke or dust can be seen through a powerful telescope."
TE = ["ఒక్క సిగరెట్ ఎప్పుడూ ఎందుకు సరిపోదు? ఎవరైనా సిగరెట్ తాగినప్పుడు, నికోటిన్ దాదాపు పది సెకన్లలో మెదడుకు చేరుతుంది.",
      "ఇంకా భయంకరమైన విషయం ఏంటంటే, వద్దు అని చెప్పాల్సిన మీలోని భాగం బలహీనపడుతుంది."]
parts=[]
for i,t in enumerate(TE):
    s=time.time(); a=np.array(m(t, ref_audio_path="voices/refs/S_006830_12s.wav", ref_text=RT), dtype=np.float32)
    if np.abs(a).max()>1.5: a=a/32768.0
    parts += [a, np.zeros(int(0.35*24000),np.float32)]
    print(i, round(len(a)/24000,1), "s in", round(time.time()-s,1), flush=True)
sf.write("out/te.wav", np.concatenate(parts), 24000)
