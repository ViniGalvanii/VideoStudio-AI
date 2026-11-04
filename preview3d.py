"""Preview rápido de GLB (sem GPU): cor da textura por face + sombreamento simples, 3 ângulos."""
import sys, numpy as np, trimesh, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

def render(glb, out):
    s = trimesh.load(glb); m = list(s.geometry.values())[0] if hasattr(s, "geometry") else s
    v = m.vertices - m.bounds.mean(0); v /= np.abs(v).max()
    f = m.faces; tri = v[f]
    try:
        tex = np.asarray(m.visual.material.baseColorTexture.convert("RGB")) / 255.0
        uv = m.visual.uv[f].mean(1); h, w = tex.shape[:2]
        col = tex[np.clip(((1 - uv[:, 1]) * (h - 1)).astype(int), 0, h - 1), np.clip((uv[:, 0] * (w - 1)).astype(int), 0, w - 1)]
    except Exception:
        col = np.full((len(f), 3), 0.7)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    fig = plt.figure(figsize=(12, 4.2), facecolor="#202225")
    for k, az in enumerate((35, 155, 275)):
        ax = fig.add_subplot(1, 3, k + 1, projection="3d"); ax.set_facecolor("#202225")
        a, e = np.radians(az), np.radians(22)
        light = np.array([np.cos(e) * np.cos(a + 0.6), np.cos(e) * np.sin(a + 0.6), np.sin(e) + 0.4]); light /= np.linalg.norm(light)
        # glTF é Y-up: troca para Z-up no matplotlib
        T = tri[:, :, [0, 2, 1]]; N = n[:, [0, 2, 1]]
        shade = 0.35 + 0.65 * np.clip(np.abs(N @ light), 0, 1)
        pc = Poly3DCollection(T, facecolors=np.clip(col * shade[:, None], 0, 1), edgecolors="none")
        ax.add_collection3d(pc); ax.set_xlim(-1, 1); ax.set_ylim(-1, 1); ax.set_zlim(-1, 1)
        ax.view_init(elev=22, azim=az); ax.set_box_aspect((1, 1, 1)); ax.axis("off")
    plt.subplots_adjust(0, 0, 1, 1, 0, 0); fig.savefig(out, dpi=90, facecolor="#202225"); plt.close(fig)

if __name__ == "__main__":
    for g in sys.argv[1:]:
        render(g, g.replace(".glb", "_preview.png")); print("ok", g)
