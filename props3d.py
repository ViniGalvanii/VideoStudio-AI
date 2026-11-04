#!/usr/bin/env python3
"""Imagem -> modelo 3D (Pixal3D/TRELLIS.2 nativos do ComfyUI) pronto para Roblox: GLB low-poly com PBR.
uso: props3d.py --pod POD img1.png [img2.png ...] [--faces 9000] [--tex 1024] [--trellis]"""
import argparse, copy, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from comfy import Comfy
from align3d import align


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pod", required=True)
    ap.add_argument("imgs", nargs="+")
    ap.add_argument("--faces", type=int, default=9000)
    ap.add_argument("--tex", type=int, default=1024)
    ap.add_argument("--trellis", action="store_true", help="usar TRELLIS.2 em vez de Pixal3D")
    a = ap.parse_args()
    c = Comfy(a.pod)
    c.wait_up()
    base = json.loads((ROOT / "workflows/img2_3d_base.json").read_text())
    for img in a.imgs:
        img = Path(img)
        name = img.stem
        wf = copy.deepcopy(base)
        wf["122"]["inputs"]["image"] = c.upload(str(img), f"prop_{name}.png")
        wf["316"]["inputs"]["value"] = a.trellis
        wf["186"]["inputs"]["target_face_count"] = a.faces      # low-poly para o Roblox
        wf["288"]["inputs"]["value"] = a.tex                     # resolução do atlas/texturas
        wf["224"]["inputs"]["resolution"] = a.tex                # normal map
        wf["233"]["inputs"]["resolution"] = a.tex                # AO
        wf["322"]["inputs"]["filename_prefix"] = f"3d/{name}"
        t0 = time.time()
        h = c.wait(c.queue(wf), timeout=3600)
        outs = c.outputs(h)
        glbs = [o for o in outs if o["filename"].lower().endswith((".glb", ".gltf"))]
        if not glbs:
            print("sem GLB na saída:", [o["filename"] for o in outs]); continue
        dest = img.with_suffix(".glb")
        c.download(glbs[-1], dest)
        align(str(dest))   # Pixal3D sai no ângulo da câmera: endireita, base em y=0, centraliza
        print(f"{name}: {dest} ({dest.stat().st_size/1e6:.1f} MB, {time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
