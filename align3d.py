"""Endireita props gerados pelo Pixal3D (malha vem no ângulo da câmera): alinha à caixa orientada mínima,
mantém 'cima' no eixo Y, apoia a base em y=0 e centraliza em X/Z. Preserva UV e materiais."""
import sys, numpy as np, trimesh

def align(path, out=None):
    s = trimesh.load(path); key = list(s.geometry.keys())[0]; m = s.geometry[key]
    to, _ = trimesh.bounds.oriented_bounds(m)            # transforma para eixos da OBB
    R = to[:3, :3]
    # escolhe qual eixo da OBB vira o Y (o mais parecido com o Y original)
    up_idx = int(np.argmax(np.abs(R[:, 1])))
    perm = {0: [1, 0, 2], 1: [0, 1, 2], 2: [0, 2, 1]}[up_idx]
    P = np.eye(4)[perm + [3]]
    T = P @ to
    if (T[:3, :3] @ np.array([0, 1, 0]))[1] < 0:        # não deixar de cabeça para baixo
        T = np.diag([1, -1, -1, 1]) @ T
    if np.linalg.det(T[:3, :3]) < 0:
        T = np.diag([-1, 1, 1, 1]) @ T
    m.apply_transform(T)
    b = m.bounds
    m.apply_translation([-(b[0, 0] + b[1, 0]) / 2, -b[0, 1], -(b[0, 2] + b[1, 2]) / 2])
    s.geometry[key] = m
    s.export(out or path)
    return m.extents

if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p, align(p).round(3).tolist())
