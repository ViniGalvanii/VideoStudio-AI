#!/usr/bin/env python3
"""Gera o body do create-pod (Runpod MCP) já com o boot.sh embutido.
O boot baixa só o que falta no volume e o ComfyUI sobe normalmente (/start.sh)."""
import base64, json, os, sys
from pathlib import Path

VOLUME = os.environ["RUNPOD_VOLUME_ID"]            # Network Volume com os modelos
TEMPLATE = os.environ["RUNPOD_TEMPLATE_ID"]        # template oficial ComfyUI (CUDA 13.0)
GPU = sys.argv[1] if len(sys.argv) > 1 else "NVIDIA RTX PRO 4500 Blackwell"

boot = base64.b64encode((Path(__file__).parent / "boot.sh").read_bytes()).decode()
body = {
    "name": "estudio-comfy",
    "templateId": TEMPLATE,
    "cloud": "SECURE",
    "dataCenterIds": [os.environ.get("RUNPOD_DATACENTER", "EU-RO-1")],
    "gpu": {"id": GPU, "count": 1, "minCudaVersion": "13.0"},
    "mounts": {"network": [{"volumeId": VOLUME, "path": "/workspace"}]},
    "disk": 50,
    "env": {"BOOT_B64": boot},
    "entrypoint": ["/bin/bash", "-c"],
    "cmd": ["echo \"$BOOT_B64\" | base64 -d > /boot.sh; bash /boot.sh pre 2>&1 | sed -u 's/^/[boot] /'; "
            "(bash /boot.sh 2>&1 | sed -u 's/^/[boot] /') & exec /start.sh"],
}
print(json.dumps(body))
