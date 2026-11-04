"""Converte um workflow de UI do ComfyUI (templates oficiais) para o formato de API, usando /object_info do servidor."""
import json

SKIP = {"Note", "MarkdownNote", "Reroute", "PrimitiveNode"}
WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO", "COLOR", "LOAD_3D", "COMFY_DYNAMICCOMBO_V3"}


def _is_widget(spec):
    t = spec[0]
    return isinstance(t, list) or t in WIDGET_TYPES


def convert(ui: dict, object_info: dict) -> dict:
    links = {l[0]: l for l in ui["links"]}
    api = {}
    for n in ui["nodes"]:
        if n["type"] in SKIP or n.get("mode") in (2, 4):
            continue
        info = object_info.get(n["type"])
        if info is None:
            raise KeyError(f"nó desconhecido no servidor: {n['type']} (id {n['id']})")
        order = info.get("input_order") or {k: list(v.keys()) for k, v in info["input"].items()}
        specs = {**info["input"].get("required", {}), **info["input"].get("optional", {})}
        names = list(order.get("required", [])) + list(order.get("optional", []))
        vals = list(n.get("widgets_values") or []) if isinstance(n.get("widgets_values"), list) else []
        inputs, k = {}, 0
        def take(name, spec):
            nonlocal k
            if spec is None or not _is_widget(spec):
                return
            if k < len(vals):
                inputs[name] = vals[k]
                k += 1
            opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            if opts.get("control_after_generate") and k < len(vals) and vals[k] in ("fixed", "randomize", "increment", "decrement"):
                k += 1
            if (opts.get("image_upload") or opts.get("upload")) and k < len(vals) and vals[k] in ("image", "video", "audio", "3d"):
                k += 1
            if spec[0] == "COMFY_DYNAMICCOMBO_V3":  # sub-entradas da opção escolhida: "nome.sub"
                opt = next((o for o in opts.get("options", []) if o["key"] == inputs.get(name)), None)
                if opt:
                    for sec in ("required", "optional"):
                        for sub, sspec in opt["inputs"].get(sec, {}).items():
                            take(f"{name}.{sub}", sspec)
        for name in names:
            take(name, specs.get(name))
        for i in n.get("inputs", []):
            if i.get("link") is not None and i["link"] in links:
                l = links[i["link"]]
                src = next((x for x in ui["nodes"] if x["id"] == l[1]), None)
                if src is None or src["type"] in SKIP:
                    continue
                inputs[i["name"]] = [str(l[1]), l[2]]
        api[str(n["id"])] = {"class_type": n["type"], "inputs": inputs}
    return api
