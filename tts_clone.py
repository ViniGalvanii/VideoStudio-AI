"""Narração com voz clonada (Chatterbox Multilingual, MIT). Roda no venv do Chatterbox.
uso: tts_clone.py <ref.wav> <saida_dir> <textos.json> [exagero] [cfg]
Gera scene_XX.wav (com marca d'água Perth do modelo)."""
import json, sys, time
import torch, torchaudio

torch.set_num_threads(max(1, torch.get_num_threads()))
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

ref, out, textos = sys.argv[1], sys.argv[2], json.load(open(sys.argv[3], encoding="utf-8"))
exag = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
cfg = float(sys.argv[5]) if len(sys.argv) > 5 else 0.5
dev = "cuda" if torch.cuda.is_available() else "cpu"
m = ChatterboxMultilingualTTS.from_pretrained(device=dev)
for i, t in textos:
    t0 = time.time()
    wav = m.generate(t, language_id="pt", audio_prompt_path=ref, exaggeration=exag, cfg_weight=cfg)
    torchaudio.save(f"{out}/scene_{i:02d}.wav", wav, m.sr)
    print(f"cena {i:02d} gerada ({time.time()-t0:.0f}s)", flush=True)
