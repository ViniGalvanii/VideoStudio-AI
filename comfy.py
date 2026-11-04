"""Cliente mínimo da API do ComfyUI rodando num pod Runpod (via proxy HTTPS)."""
import json, os, time, uuid
import requests

VERIFY = os.environ.get("REQUESTS_CA_BUNDLE") or True


class Comfy:
    def __init__(self, pod_id: str):
        self.base = f"https://{pod_id}-8188.proxy.runpod.net"
        self.cid = uuid.uuid4().hex
        self.s = requests.Session()
        self.s.verify = VERIFY

    def up(self) -> bool:
        try:
            r = self.s.get(self.base + "/system_stats", timeout=20)
            return r.ok and "system" in r.json()
        except Exception:
            return False

    def wait_up(self, timeout=900):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.up():
                return True
            time.sleep(10)
        raise TimeoutError("ComfyUI não respondeu")

    def models(self, folder: str) -> list:
        r = self.s.get(f"{self.base}/models/{folder}", timeout=30)
        return r.json() if r.ok else []

    def upload(self, path: str, name: str) -> str:
        with open(path, "rb") as f:
            r = self.s.post(self.base + "/upload/image",
                            files={"image": (name, f, "image/png")},
                            data={"overwrite": "true"}, timeout=120)
        r.raise_for_status()
        return r.json()["name"]

    def queue(self, wf: dict) -> str:
        r = self.s.post(self.base + "/prompt", json={"prompt": wf, "client_id": self.cid}, timeout=60)
        if not r.ok:
            raise RuntimeError(f"/prompt {r.status_code}: {r.text[:800]}")
        return r.json()["prompt_id"]

    def wait(self, pid: str, timeout=1800) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout:
            r = self.s.get(f"{self.base}/history/{pid}", timeout=30)
            h = r.json().get(pid) if r.ok else None
            if h:
                st = h.get("status", {})
                if st.get("status_str") == "error":
                    msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                    raise RuntimeError(f"Erro no ComfyUI: {json.dumps(msgs)[:1500]}")
                if st.get("completed"):
                    return h
            time.sleep(4)
        raise TimeoutError(f"prompt {pid} passou de {timeout}s")

    def outputs(self, hist: dict) -> list:
        files = []
        for node in hist.get("outputs", {}).values():
            for v in node.values():
                if isinstance(v, list):
                    files += [x for x in v if isinstance(x, dict) and "filename" in x]
        return files

    def download(self, f: dict, dest: str):
        r = self.s.get(self.base + "/view", params={"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                                    "type": f.get("type", "output")}, timeout=300, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as o:
            for chunk in r.iter_content(1 << 20):
                o.write(chunk)
        return dest
