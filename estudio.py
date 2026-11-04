#!/usr/bin/env python3
"""Estúdio de vídeos dark: roteiro.json -> narração -> keyframes -> animação -> vídeo final 9:16.

Uso (o Claude roda isso por você):
  python3 estudio.py voz      <projeto> [--lang pt|en]
  python3 estudio.py keyframes <projeto> --pod POD_ID [--cenas 1,4] [--seed N]
  python3 estudio.py animar   <projeto> --pod POD_ID [--cenas 2,3]
  python3 estudio.py montar   <projeto> [--lang pt|en]
  python3 estudio.py checar   --pod POD_ID
  python3 estudio.py custo    <projeto>
"""
import argparse, asyncio, copy, json, math, os, random, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJ = ROOT / "projetos"
PRECO_H = 0.72          # US$/h do pod atual (RTX PRO 4500 Secure)
SEG_KF = 8              # s por keyframe (Flux schnell, após carregar)
SEG_CLIP = 120          # s por clipe Wan 2.2 480x832 81f 4 steps
W, H, FPS = 1080, 1920, 30
GAP, END_PAD = 0.35, 1.0


# ----------------------------------------------------------------- utilidades
def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Falhou: {' '.join(map(str, cmd))[:300]}\n{r.stderr[-1500:]}")
    return r.stdout


def dur(path):
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).strip())


def load(proj):
    p = PROJ / proj
    rot = json.loads((p / "roteiro.json").read_text(encoding="utf-8"))
    return p, rot


def sel(rot, cenas):
    idx = range(1, len(rot["cenas"]) + 1)
    if cenas:
        want = {int(x) for x in cenas.split(",")}
        idx = [i for i in idx if i in want]
    return list(idx)


def log(*a):
    print(*a, flush=True)


# ----------------------------------------------------------------------- voz
async def _tts(text, voice, rate, out_mp3):
    import edge_tts
    c = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(out_mp3, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append([round(ch["offset"] / 1e7, 3), round(ch["duration"] / 1e7, 3), ch["text"]])
    return words


TTS_PY = Path(os.environ.get("TTS_PYTHON", "python"))   # python do venv com Chatterbox
_WHISPER = None


def word_times(audio_path, lang="pt"):
    """Tempos por palavra via faster-whisper (para vozes sem WordBoundary, ex.: clonada)."""
    global _WHISPER
    import numpy as np
    from faster_whisper import WhisperModel
    if _WHISPER is None:
        _WHISPER = WhisperModel("small", device="cpu", compute_type="int8")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio_path), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True).stdout
    audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    segs, _ = _WHISPER.transcribe(audio, language=lang, word_timestamps=True)
    return [[round(w.start, 3), round(w.end - w.start, 3), w.word.strip(" ,.;:!?")] for s in segs for w in s.words]


def align_text(text, words):
    """Legenda usa o TEXTO DO ROTEIRO (grafia certa) com os tempos do whisper, alinhados por posição de caractere."""
    toks = [t for t in text.replace("—", " ").split() if t.strip(" ,.;:!?\"'")]
    toks = [t.strip(" \"'") for t in toks]
    if not words or not toks:
        return words
    if len(words) == len(toks):
        return [[w[0], w[1], t.rstrip(",.;:?!")] for w, t in zip(words, toks)]
    def cum(seq):
        tot = sum(len(s) + 1 for s in seq); acc, out = 0, []
        for s in seq:
            out.append(acc / tot); acc += len(s) + 1
        return out + [1.0]
    wf = cum([w[2] for w in words])
    t_start = [w[0] for w in words] + [words[-1][0] + words[-1][1]]
    def at(frac):
        for k in range(len(wf) - 1):
            if wf[k] <= frac <= wf[k + 1]:
                r = (frac - wf[k]) / max(wf[k + 1] - wf[k], 1e-6)
                return t_start[k] + r * (t_start[k + 1] - t_start[k])
        return t_start[-1]
    tf = cum(toks)
    out = []
    for k, t in enumerate(toks):
        s, e = at(tf[k]), at(tf[k + 1])
        out.append([round(s, 3), round(max(e - s, 0.05), 3), t.rstrip(",.;:?!")])
    return out


def voz_clone(p, rot, ref, cenas_idx):
    """Gera narração com voz clonada (Chatterbox) e corta silêncio de borda."""
    out = p / "audio_pt"
    out.mkdir(exist_ok=True)
    jobs = [[i, rot["cenas"][i - 1]["texto"]] for i in cenas_idx]
    jf = p / "_tts_jobs.json"
    jf.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ)
    proc = subprocess.Popen([str(TTS_PY), str(ROOT / "tts_clone.py"), str(ROOT / ref), str(out), str(jf),
                             str(rot.get("clone_exagero", 0.5)), str(rot.get("clone_cfg", 0.5))],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    for line in proc.stdout:
        if line.startswith("cena"):
            log(line.strip())
    if proc.wait() != 0:
        raise RuntimeError("Chatterbox falhou")
    for i in cenas_idx:
        wav, mp3 = out / f"scene_{i:02d}.wav", out / f"scene_{i:02d}.mp3"
        sh(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af",
            "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
            "loudnorm=I=-16:TP=-1.5", "-ar", "48000", "-b:a", "192k", str(mp3)])
        raw = word_times(mp3)
        (out / f"scene_{i:02d}.whisper.json").write_text(json.dumps(raw, ensure_ascii=False))
        words = align_text(rot["cenas"][i - 1]["texto"], raw)
        (out / f"scene_{i:02d}.json").write_text(json.dumps(words, ensure_ascii=False))
        log(f"cena {i:02d}: {dur(mp3):5.2f}s · {len(words)} palavras")


def cmd_voz(a):
    p, rot = load(a.projeto)
    lang = a.lang
    key = "texto" if lang == "pt" else f"texto_{lang}"
    voice = rot.get("voz" if lang == "pt" else f"voz_{lang}", "pt-BR-AntonioNeural" if lang == "pt" else "en-US-ChristopherNeural")
    if lang == "pt" and voice.startswith("clone:"):
        voz_clone(p, rot, voice.split(":", 1)[1], sel(rot, a.cenas))
        return
    rate = rot.get("velocidade", "+0%")
    out = p / f"audio_{lang}"
    out.mkdir(exist_ok=True)
    total = 0
    for i, c in enumerate(rot["cenas"], 1):
        txt = c.get(key)
        if not txt:
            raise SystemExit(f"Cena {i} sem '{key}'")
        mp3 = out / f"scene_{i:02d}.mp3"
        for tent in range(3):
            try:
                words = asyncio.run(_tts(txt, voice, rate, mp3))
                break
            except Exception as e:
                if tent == 2:
                    raise
                time.sleep(3)
        (out / f"scene_{i:02d}.json").write_text(json.dumps(words, ensure_ascii=False))
        d = dur(mp3)
        total += d + GAP
        log(f"cena {i:02d}: {d:5.2f}s")
    log(f"narração total ≈ {total + END_PAD:.1f}s ({voice})")


# ------------------------------------------------------------- comfy (pod)
def _comfy(pod):
    sys.path.insert(0, str(ROOT))
    from comfy import Comfy
    c = Comfy(pod)
    log(f"conectando em {c.base} ...")
    c.wait_up()
    return c


QWEN_UNET = "qwen_image_edit_2511_fp8_e4m3fn_scaled_lightning_comfyui_4steps_v1.0.safetensors"


def cmd_checar(a):
    c = _comfy(a.pod)
    need = {"checkpoints": ["flux1-schnell-fp8.safetensors"],
            "diffusion_models": ["wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", QWEN_UNET],
            "text_encoders": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors", "qwen_2.5_vl_7b_fp8_scaled.safetensors"],
            "vae": ["wan_2.1_vae.safetensors", "qwen_image_vae.safetensors"],
            "loras": ["wan2.2_i2v_lightx2v_motion_fix_high.safetensors", "wan2.2_i2v_lightx2v_motion_fix_low.safetensors"]}
    ok = True
    for folder, files in need.items():
        have = set(c.models(folder))
        for f in files:
            st = "ok" if f in have else "FALTA"
            ok &= f in have
            log(f"{st:5} {folder}/{f}")
    log("PRONTO" if ok else "AINDA BAIXANDO (boot) — tente de novo em alguns minutos")


def contact_sheet(p, n):
    from PIL import Image, ImageDraw, ImageFont
    ims = []
    for i in range(1, n + 1):
        f = p / "kf" / f"scene_{i:02d}.png"
        im = Image.open(f).convert("RGB") if f.exists() else Image.new("RGB", (720, 1280), (40, 40, 40))
        im = im.resize((270, 480))
        d = ImageDraw.Draw(im)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        d.rectangle([0, 0, 70, 52], fill=(0, 0, 0))
        d.text((10, 4), str(i), fill=(255, 220, 0), font=font)
        ims.append(im)
    cols = min(5, n)
    rows = math.ceil(n / cols)
    sheet = Image.new("RGB", (cols * 274, rows * 484), (15, 15, 15))
    for k, im in enumerate(ims):
        sheet.paste(im, ((k % cols) * 274 + 2, (k // cols) * 484 + 2))
    out = p / "keyframes_contato.jpg"
    sheet.save(out, quality=88)
    return out


def flux_wf(prompt, seed, prefix):
    wf = json.loads((ROOT / "workflows/flux_t2i.json").read_text())
    wf["2"]["inputs"]["text"] = prompt
    wf["5"]["inputs"]["seed"] = seed
    wf["7"]["inputs"]["filename_prefix"] = prefix
    return wf


def qwen_wf(prompt, ref_names, seed, prefix, w=720, h=1280):
    """Qwen-Image-Edit 2511 (4 steps embutidos) gerando cena nova a partir de 1–3 fichas de personagem."""
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": QWEN_UNET, "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.1}},
        "3": {"class_type": "CFGNorm", "inputs": {"model": ["2", 0], "strength": 1.0}},
        "4": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image", "device": "default"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "13": {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "14": {"class_type": "KSampler", "inputs": {"model": ["3", 0], "positive": ["11", 0], "negative": ["12", 0],
               "latent_image": ["13", 0], "seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler",
               "scheduler": "simple", "denoise": 1.0}},
        "15": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["5", 0]}},
        "16": {"class_type": "SaveImage", "inputs": {"images": ["15", 0], "filename_prefix": prefix}},
    }
    pos = {"clip": ["4", 0], "prompt": prompt, "vae": ["5", 0]}
    neg = {"clip": ["4", 0], "prompt": "", "vae": ["5", 0]}
    for k, name in enumerate(ref_names[:3], 1):
        nid = str(20 + k)
        wf[nid] = {"class_type": "LoadImage", "inputs": {"image": name}}
        pos[f"image{k}"] = [nid, 0]
        neg[f"image{k}"] = [nid, 0]
    wf["9"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": pos}
    wf["10"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": neg}
    wf["11"] = {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {"conditioning": ["9", 0], "reference_latents_method": "index_timestep_zero"}}
    wf["12"] = {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {"conditioning": ["10", 0], "reference_latents_method": "index_timestep_zero"}}
    return wf


def _run_images(c, jobs, dest_fn, label):
    t0 = time.time()
    for key, pid in jobs:
        h = c.wait(pid)
        f = [x for x in c.outputs(h) if x["filename"].endswith(".png")][0]
        c.download(f, dest_fn(key))
        log(f"{label} {key} ok ({time.time()-t0:.0f}s)")


def cmd_fichas(a):
    """Ficha de personagem (corpo inteiro, fundo neutro) via Flux — vira referência fixa das cenas."""
    p, rot = load(a.projeto)
    chars = rot.get("personagens", {})
    names = [n for n in chars if not a.nomes or n in a.nomes.split(",")]
    c = _comfy(a.pod)
    (p / "personagens").mkdir(exist_ok=True)
    base = a.seed if a.seed is not None else random.randint(1, 2**31)
    jobs = []
    for k, n in enumerate(names):
        prompt = (f"character reference photo, full body standing front view, {chars[n]['descricao']}, "
                  f"face clearly visible, neutral plain light gray studio background, soft even lighting, "
                  f"realistic cinematic film still, highly detailed, no text")
        jobs.append((n, c.queue(flux_wf(prompt, chars[n].get("seed", base + k), f"fichas/{a.projeto}_{n}"))))
    _run_images(c, jobs, lambda n: p / "personagens" / f"{n}.png", "ficha")
    from PIL import Image
    ims = [Image.open(p / "personagens" / f"{n}.png").convert("RGB").resize((360, 640)) for n in chars
           if (p / "personagens" / f"{n}.png").exists()]
    sheet = Image.new("RGB", (364 * len(ims), 644), (15, 15, 15))
    for k, im in enumerate(ims):
        sheet.paste(im, (k * 364 + 2, 2))
    sheet.save(p / "fichas_contato.jpg", quality=88)
    log(f"contato: {p / 'fichas_contato.jpg'}")


def cmd_keyframes(a):
    p, rot = load(a.projeto)
    idx = sel(rot, a.cenas)
    est = len(idx) * 20 + 90
    log(f"{len(idx)} keyframes · estimativa {est/60:.1f} min · ~US${est/3600*PRECO_H:.2f}")
    c = _comfy(a.pod)
    (p / "kf").mkdir(exist_ok=True)
    estilo = rot.get("estilo_imagem", "")
    chars = rot.get("personagens", {})
    uploaded = {}
    for n in chars:
        f = p / "personagens" / f"{n}.png"
        if f.exists():
            uploaded[n] = c.upload(str(f), f"{a.projeto}_ficha_{n}.png")
    base = a.seed if a.seed is not None else random.randint(1, 2**31)
    jobs = []
    if a.fins:  # quadro FINAL (para animação primeiro→último quadro): edição do keyframe inicial
        for i in idx:
            cena = rot["cenas"][i - 1]
            if not cena.get("fim") or not (p / "kf" / f"scene_{i:02d}.png").exists():
                continue
            start = c.upload(str(p / "kf" / f"scene_{i:02d}.png"), f"{a.projeto}_s{i:02d}.png")
            who = [n for n in cena.get("personagens", []) if n in uploaded]
            refs = "".join(f" image {k} is {chars[n].get('nome', n)}." for k, n in enumerate(who, 2))
            prompt = (f"Same scene, same camera angle, same lighting and same characters as image 1, a moment later: "
                      f"{cena['fim']}.{refs} Keep faces, clothing and environment identical. {estilo}")
            wf = qwen_wf(prompt, [start] + [uploaded[n] for n in who], cena.get("seed", base + i) + 7, f"kf/{a.projeto}_s{i:02d}_end")
            jobs.append((i, c.queue(wf)))
        _run_images(c, jobs, lambda i: p / "kf" / f"scene_{i:02d}_end.png", "quadro final")
        return
    for i in idx:
        cena = rot["cenas"][i - 1]
        seed = cena.get("seed", base + i)
        prefix = f"kf/{a.projeto}_s{i:02d}"
        who = [n for n in cena.get("personagens", []) if n in uploaded]
        kref = cena.get("ref_kf", [])   # outros keyframes como referência visual (ex.: muralhas de água, carruagem)
        if kref or cena.get("motor") == "qwen":
            names, labels = [], []
            for r_ in kref:
                names.append(c.upload(str(p / "kf" / f"scene_{r_['cena']:02d}.png"), f"{a.projeto}_ref{r_['cena']:02d}.png"))
                labels.append(f"image {len(names)} shows {r_['uso']}")
            for n in who:
                names.append(uploaded[n]); labels.append(f"image {len(names)} is {chars[n].get('nome', n)}")
            prompt = (f"Create a new vertical realistic photograph: {cena['imagem']}. " + ("; ".join(labels) + ". " if labels else "")
                      + f"Match the referenced elements exactly. Not a painting, not CGI. {estilo}")
            wf = qwen_wf(prompt, names[:3], seed, prefix)
        elif who:
            refs = "; ".join(f"image {k} is {chars[n].get('nome', n)}" for k, n in enumerate(who, 1))
            prompt = (f"Create a new vertical cinematic scene: {cena['imagem']}. {refs}. Keep exactly the same face, "
                      f"hair, age, body and clothing as in the reference images. Realistic photograph, natural skin texture, not a painting, not CGI. {estilo}")
            wf = qwen_wf(prompt, [uploaded[n] for n in who], seed, prefix)
        else:
            wf = flux_wf(", ".join(x for x in [cena["imagem"], estilo] if x), seed, prefix)
        jobs.append((i, c.queue(wf)))
    _run_images(c, jobs, lambda i: p / "kf" / f"scene_{i:02d}.png", "keyframe")
    sheet = contact_sheet(p, len(rot["cenas"]))
    log(f"contato: {sheet}")


def cmd_animar(a):
    p, rot = load(a.projeto)
    idx = [i for i in sel(rot, a.cenas) if rot["cenas"][i - 1].get("animar", True)]
    miss = [i for i in idx if not (p / "kf" / f"scene_{i:02d}.png").exists()]
    if miss:
        raise SystemExit(f"Sem keyframe nas cenas {miss} — rode keyframes antes")
    est = len(idx) * SEG_CLIP + 120
    log(f"{len(idx)} clipes · estimativa {est/60:.0f} min · ~US${est/3600*PRECO_H:.2f}")
    c = _comfy(a.pod)
    wf0 = json.loads((ROOT / "workflows/wan_i2v.json").read_text())
    (p / "clips").mkdir(exist_ok=True)
    jobs = []
    for i in idx:
        cena = rot["cenas"][i - 1]
        name = c.upload(str(p / "kf" / f"scene_{i:02d}.png"), f"{a.projeto}_s{i:02d}.png")
        wf = copy.deepcopy(wf0)
        wf["11"]["inputs"]["image"] = name
        wf["8"]["inputs"]["text"] = cena.get("movimento") or "slow cinematic push-in, subtle natural motion"
        wf["13"]["inputs"]["noise_seed"] = random.randint(1, 2**31)
        wf["13"]["inputs"].pop("control_after_generate", None)
        # duração do clipe = narração da cena (sem esticar depois); frames em 4k+1, 33..81
        mp3 = p / "audio_pt" / f"scene_{i:02d}.mp3"
        need = (dur(mp3) + GAP) if mp3.exists() else 5.0
        frames = min(81, max(33, 4 * math.ceil(need * 16 / 4) + 1))
        wf["12"]["inputs"]["length"] = frames
        wf["17"]["inputs"]["filename_prefix"] = f"clips/{a.projeto}_s{i:02d}"
        end = p / "kf" / f"scene_{i:02d}_end.png"
        if cena.get("fim") and end.exists():  # anima do quadro A até o quadro B (movimento controlado)
            end_name = c.upload(str(end), f"{a.projeto}_s{i:02d}_end.png")
            wf["19"] = {"class_type": "LoadImage", "inputs": {"image": end_name}}
            inp = wf["12"]["inputs"]
            wf["12"] = {"class_type": "WanFirstLastFrameToVideo", "inputs": {
                "positive": inp["positive"], "negative": inp["negative"], "vae": inp["vae"],
                "width": inp["width"], "height": inp["height"], "length": inp["length"], "batch_size": 1,
                "start_image": inp["start_image"], "end_image": ["19", 0]}}
        if rot.get("rife", False):  # interpolação RIFE: 16 → 32 fps
            wf["18"] = {"class_type": "RIFE VFI", "inputs": {"ckpt_name": "rife49.pth", "frames": ["15", 0],
                        "clear_cache_after_n_frames": 10, "multiplier": 2, "fast_mode": True,
                        "ensemble": True, "scale_factor": 1.0, "dtype": "float16",
                        "torch_compile": False, "batch_size": 8}}
            wf["16"]["inputs"]["images"] = ["18", 0]
            wf["16"]["inputs"]["fps"] = 32
        jobs.append((i, c.queue(wf)))
    t0 = time.time()
    for i, pid in jobs:
        h = c.wait(pid, timeout=3600)
        vids = [x for x in c.outputs(h) if x["filename"].rsplit(".", 1)[-1] in ("mp4", "webm", "mov")]
        c.download(vids[0], p / "clips" / f"scene_{i:02d}.mp4")
        log(f"clipe {i:02d} ok ({(time.time()-t0)/60:.1f} min)")


def cmd_custo(a):
    p, rot = load(a.projeto)
    n = len(rot["cenas"])
    na = sum(1 for c in rot["cenas"] if c.get("animar", True))
    s = n * SEG_KF + na * SEG_CLIP + 300
    log(f"{n} cenas ({na} animadas) · GPU ~{s/60:.0f} min · ~US${s/3600*PRECO_H:.2f}")


# ------------------------------------------------------------------ montagem
def ass_time(t):
    t = max(0, t)
    return f"{int(t//3600)}:{int(t%3600//60):02d}:{t%60:05.2f}"


def build_ass(chunks, out):
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,82,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,6,3,2,80,80,600,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for words in chunks:            # words: [(start, end, text)]
        for k, (s, e, _) in enumerate(words):
            end = words[k + 1][0] if k + 1 < len(words) else e
            txt = " ".join(("{\\c&H0000E5FF&}" + w.upper() + "{\\c&H00FFFFFF&}") if j == k else w.upper()
                           for j, (_, _, w) in enumerate(words))
            lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(end)},Cap,,0,0,0,,{txt}")
    out.write_text(hdr + "\n".join(lines) + "\n", encoding="utf-8")


def group_words(words, t0, maxw=3):
    chunks, cur = [], []
    for k, (off, d, w) in enumerate(words):
        s, e = t0 + off, t0 + off + d
        if cur and (len(cur) >= maxw or s - cur[-1][1] > 0.35):
            chunks.append(cur)
            cur = []
        cur.append((s, e, w))
    if cur:
        chunks.append(cur)
    return chunks


def seg_from_clip(clip, d, out, impacto=False):
    L = dur(clip)
    f = min(max(d / L, 1.0), 1.1)   # no máximo 10% mais lento: movimento fica natural
    base = f"setpts={f:.4f}*PTS,fps={FPS}"
    if L * f >= d:
        vf = f"{base},trim=duration={d:.3f},setpts=PTS-STARTPTS"
    else:  # ida e volta (ping-pong) até cobrir a narração
        vf = (f"{base},split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1,"
              f"loop=loop=-1:size=32767,trim=duration={d:.3f},setpts=PTS-STARTPTS")
    vf += (f",scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
           f"eq=contrast=1.06:saturation=1.06,vignette=PI/5")
    if impacto:  # tremor de câmera nos primeiros 0,8s + flash branco no corte
        vf += (f",scale={W+60}:{H+106},crop={W}:{H}:x='30+if(lt(t,0.8),24*sin(t*47)*(0.8-t),0)'"
               f":y='53+if(lt(t,0.8),24*cos(t*53)*(0.8-t),0)',fade=t=in:st=0:d=0.18:color=white")
    vf += ",format=yuv420p"
    sh(["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]",
        "-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out)])


def seg_from_image(img, d, out, i):
    n = max(1, round(d * FPS))
    z = 0.14
    zexpr = [f"1+{z}*on/{n}", f"{1+z}-{z}*on/{n}", f"1.08+0.04*on/{n}"][i % 3]
    xexpr = ["iw/2-(iw/zoom/2)", "iw/2-(iw/zoom/2)", f"(iw-iw/zoom)*on/{n}"][i % 3]
    vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase:flags=lanczos,crop={W*2}:{H*2},"
          f"zoompan=z='{zexpr}':x='{xexpr}':y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps={FPS},"
          f"eq=contrast=1.06:saturation=1.06,vignette=PI/5,format=yuv420p")
    sh(["ffmpeg", "-y", "-v", "error", "-i", str(img), "-vf", vf, "-frames:v", str(n), "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out)])


def cmd_montar(a):
    p, rot = load(a.projeto)
    lang = a.lang
    ad = p / f"audio_{lang}"
    tmp = p / f"_build_{lang}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    n = len(rot["cenas"])
    t, chunks, concat_v, concat_a, events = 0.0, [], [], [], []
    for i in range(1, n + 1):
        mp3 = ad / f"scene_{i:02d}.mp3"
        if not mp3.exists():
            raise SystemExit(f"Falta narração da cena {i} — rode 'voz' antes")
        da = dur(mp3)
        d = da + (END_PAD if i == n else GAP)
        words = json.loads((ad / f"scene_{i:02d}.json").read_text())
        chunks += group_words(words, t)
        seg = tmp / f"seg_{i:02d}.mp4"
        clip, kf = p / "clips" / f"scene_{i:02d}.mp4", p / "kf" / f"scene_{i:02d}.png"
        if clip.exists():
            seg_from_clip(clip, d, seg, rot["cenas"][i - 1].get("impacto", False)); kind = "clipe"
        elif kf.exists():
            seg_from_image(kf, d, seg, i); kind = "ken burns"
        else:
            raise SystemExit(f"Cena {i} sem keyframe nem clipe")
        wav = tmp / f"a_{i:02d}.wav"
        sh(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-af", f"apad=whole_dur={d:.3f}", "-t", f"{d:.3f}",
            "-ar", "48000", "-ac", "2", str(wav)])
        concat_v.append(f"file '{seg.name}'"); concat_a.append(f"file '{wav.name}'")
        log(f"cena {i:02d}: {d:5.2f}s · {kind}")
        cena = rot["cenas"][i - 1]
        if cena.get("impacto"):
            events.append(("impacto", t))
        if cena.get("sfx") == "whoosh":
            events.append(("whoosh", t))
        t += d
    (tmp / "v.txt").write_text("\n".join(concat_v)); (tmp / "a.txt").write_text("\n".join(concat_a))
    sh(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "v.txt"), "-c", "copy", str(tmp / "video.mp4")])
    sh(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "a.txt"), str(tmp / "narr.wav")])
    build_ass(chunks, tmp / "subs.ass")

    music = rot.get("musica")
    music = (p / music) if music else next(iter(sorted(p.glob("musica*.mp3"))), None)
    inputs = ["-i", str(tmp / "video.mp4"), "-i", str(tmp / "narr.wav")]
    nxt = 2
    fx_on = rot.get("efeitos", False)
    pre = "[0:v]"
    vparts = []
    if rot.get("realismo", False):  # grade de filme + aberração sutil + câmera na mão (micro tremor contínuo)
        vparts.append(f"{pre}eq=saturation=0.9:contrast=0.97:gamma=1.02,"
                      f"curves=r='0/0.03 0.5/0.52 1/0.97':g='0/0.02 0.5/0.5 1/0.96':b='0/0.05 0.5/0.48 1/0.93',"
                      f"rgbashift=rh=-2:bh=2,scale={W+40}:{H+72},"
                      f"crop={W}:{H}:x='20+6*sin(t*1.3)+3*sin(t*3.7)':y='36+5*cos(t*1.1)+3*sin(t*2.9)'[rv]")
        pre = "[rv]"
    if fx_on:  # poeira/brasas + luz quente (blend screen) + grão de filme
        sys.path.insert(0, str(ROOT))
        import fx
        inputs += ["-stream_loop", "-1", "-i", str(fx.overlay())]
        vparts.append(f"{pre}format=gbrp[b];[{nxt}:v]scale={W}:{H},fps={FPS},format=gbrp[o];"
                      f"[b][o]blend=all_mode=screen:all_opacity=0.5,format=yuv420p,noise=alls=6:allf=t+u[fxv]")
        pre, nxt = "[fxv]", nxt + 1
    vparts.append(f"{pre}ass={tmp/'subs.ass'},fade=t=in:st=0:d=0.3,fade=t=out:st={t-0.6:.2f}:d=0.6[v]")
    vf = ";".join(vparts)
    beds, sfxs = [], []   # camadas de áudio extras sob a narração
    apre = []
    if music and Path(music).exists():
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        apre.append(f"[{nxt}:a]volume=0.22,afade=t=out:st={t-1.5:.2f}:d=1.5,aformat=channel_layouts=stereo[mus]")
        beds.append("[mus]"); nxt += 1
    if fx_on:
        imp, who, ven = fx.sfx()
        inputs += ["-stream_loop", "-1", "-i", str(ven)]
        apre.append(f"[{nxt}:a]volume=0.10[ven]"); beds.append("[ven]"); nxt += 1
        for k, (kind, at) in enumerate(events):
            inputs += ["-i", str(imp if kind == "impacto" else who)]
            ms = int(at * 1000)
            apre.append(f"[{nxt}:a]adelay={ms}|{ms},volume={0.9 if kind == 'impacto' else 0.6}[e{k}]")
            sfxs.append(f"[e{k}]"); nxt += 1
    if beds:   # trilha/vento abaixam quando a narração fala (ducking); efeitos sonoros não
        bed = (f"{''.join(beds)}amix=inputs={len(beds)}:duration=longest:normalize=0[bed];" if len(beds) > 1
               else f"{beds[0]}anull[bed];")
        mix = ["[n1]", "[bd]"] + sfxs
        af = (";".join(apre) + ";" + bed +
              f"[1:a]asplit[n1][n2];[bed][n2]sidechaincompress=threshold=0.05:ratio=4:attack=15:release=300[bd];"
              f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    else:
        af = "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    out = p / f"final_{lang}.mp4"
    sh(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]",
        "-t", f"{t:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)])
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"FINAL: {out} · {dur(out):.1f}s · {out.stat().st_size/1e6:.1f} MB")


# ----------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("voz"); s.add_argument("projeto"); s.add_argument("--lang", default="pt"); s.add_argument("--cenas")
    s.set_defaults(f=cmd_voz)
    s = sp.add_parser("fichas"); s.add_argument("projeto"); s.add_argument("--pod", required=True)
    s.add_argument("--nomes"); s.add_argument("--seed", type=int); s.set_defaults(f=cmd_fichas)
    s = sp.add_parser("keyframes"); s.add_argument("projeto"); s.add_argument("--pod", required=True)
    s.add_argument("--cenas"); s.add_argument("--seed", type=int); s.add_argument("--fins", action="store_true")
    s.set_defaults(f=cmd_keyframes)
    s = sp.add_parser("animar"); s.add_argument("projeto"); s.add_argument("--pod", required=True)
    s.add_argument("--cenas"); s.set_defaults(f=cmd_animar)
    s = sp.add_parser("montar"); s.add_argument("projeto"); s.add_argument("--lang", default="pt"); s.set_defaults(f=cmd_montar)
    s = sp.add_parser("checar"); s.add_argument("--pod", required=True); s.set_defaults(f=cmd_checar)
    s = sp.add_parser("custo"); s.add_argument("projeto"); s.set_defaults(f=cmd_custo)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
