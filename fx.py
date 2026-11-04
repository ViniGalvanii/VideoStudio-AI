"""Efeitos 100% procedurais (sem material de terceiros): poeira/brasas + luz vazando, e sons sintetizados."""
import subprocess
from pathlib import Path
import numpy as np

ASSETS = Path(__file__).resolve().parent / "assets"


def _ff(args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def overlay(seconds=12, fps=30, w=540, h=960, seed=7):
    """Camada de partículas de poeira dourada + manchas de luz quente, fundo preto (para blend 'screen')."""
    out = ASSETS / "fx_overlay.mp4"
    if out.exists():
        return out
    ASSETS.mkdir(exist_ok=True)
    rng = np.random.default_rng(seed)
    n = 140
    x, y = rng.uniform(0, w, n), rng.uniform(0, h, n)
    vx, vy = rng.normal(6, 5, n), rng.uniform(-22, -6, n)        # deriva lateral e subida lenta (px/s)
    size = rng.uniform(1.0, 3.6, n)
    bright = rng.uniform(0.35, 1.0, n)
    phase = rng.uniform(0, 6.28, n)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # luz vazando: dois blobs quentes que passeiam devagar
    blobs = [(0.15, 0.2, 0.55, 0.11, 0.9), (0.85, 0.75, 0.45, 0.07, 2.1)]
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-vf", "gblur=sigma=1.2", "-c:v", "libx264", "-crf", "16",
                          "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    total = seconds * fps
    for f in range(total):
        t = f / fps
        frame = np.zeros((h, w, 3), np.float32)
        for bx, by, r, amp, sp in blobs:
            cx = (bx + 0.08 * np.sin(t * 0.4 * sp)) * w
            cy = (by + 0.06 * np.cos(t * 0.3 * sp)) * h
            g = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (r * w) ** 2))) * amp
            frame += g[..., None] * np.array([255, 150, 60], np.float32)
        px = (x + vx * t) % w
        py = (y + vy * t) % h
        tw = bright * (0.6 + 0.4 * np.sin(t * 3 + phase))
        for k in range(n):
            x0, y0, s = int(px[k]), int(py[k]), size[k]
            r = int(s * 2) + 1
            ys, xs = slice(max(0, y0 - r), min(h, y0 + r)), slice(max(0, x0 - r), min(w, x0 + r))
            d2 = (xx[ys, xs] - px[k]) ** 2 + (yy[ys, xs] - py[k]) ** 2
            frame[ys, xs] += (np.exp(-d2 / (s * s)) * tw[k])[..., None] * np.array([255, 215, 150], np.float32)
        # loop sem emenda: fade nas bordas do ciclo
        edge = min(1.0, f / fps / 0.5, (total - f) / fps / 0.5)
        p.stdin.write(np.clip(frame * edge, 0, 255).astype(np.uint8).tobytes())
    p.stdin.close(); p.wait()
    return out


def sfx():
    """impacto (boom grave), whoosh (giro/arremesso) e vento (ambiente em loop)."""
    ASSETS.mkdir(exist_ok=True)
    imp, who, ven = ASSETS / "sfx_impacto.wav", ASSETS / "sfx_whoosh.wav", ASSETS / "sfx_vento.wav"
    if not imp.exists():
        _ff(["-f", "lavfi", "-i", "aevalsrc='0.9*sin(2*PI*(60-35*t)*t)*exp(-3.5*t)':s=48000:d=1.6",
             "-f", "lavfi", "-i", "anoisesrc=c=brown:a=0.8:d=1.6:r=48000",
             "-filter_complex", "[1]lowpass=f=300,afade=t=out:st=0.05:d=0.9[n];[0][n]amix=inputs=2:normalize=0,"
                                "alimiter=limit=0.9,aformat=channel_layouts=stereo", str(imp)])
    if not who.exists():
        _ff(["-f", "lavfi", "-i", "anoisesrc=c=pink:a=0.7:d=0.7:r=48000",
             "-af", "bandpass=f=900:w=1.2:t=o,afade=t=in:d=0.35,afade=t=out:st=0.35:d=0.35,volume=1.6,"
                    "aformat=channel_layouts=stereo", str(who)])
    if not ven.exists():
        _ff(["-f", "lavfi", "-i", "anoisesrc=c=brown:a=0.5:d=20:r=48000",
             "-af", "lowpass=f=500,tremolo=f=0.15:d=0.5,afade=t=in:d=1,afade=t=out:st=19:d=1,"
                    "aformat=channel_layouts=stereo", str(ven)])
    return imp, who, ven
