# Guia de prompts — menos "cara de IA"

## 1. Imagem (Flux / Qwen) — linguagem de FOTÓGRAFO, não de "arte IA"
Evitar (deixam o visual plastificado): `epic, masterpiece, 8k, ultra detailed, hyperrealistic, cinematic lighting,
dramatic golden hour` em TODAS as cenas, `highly detailed`, simetria perfeita, pose de herói.

Usar:
- **Câmera real:** `photograph, shot on 35mm film, Kodak Portra 400, 50mm lens, f/2.8, natural light`
- **Imperfeição:** `natural skin texture, visible pores, sun-weathered skin, dust and sweat, worn and patched
  wool clothing, dirt under fingernails, uneven terrain`
- **Momento cândido:** `candid moment, caught mid-action, slightly off-center composition, subject not looking at camera`
- **Luz variada por cena** (golden hour em tudo denuncia IA): `overcast soft light`, `harsh midday sun with hard
  shadows`, `blue hour`, `oil lamp light`, `dusty backlight`
- **Paleta contida:** `muted earthy colors, slightly desaturated, low contrast`
- **Figurantes:** `varied ordinary faces, different ages and builds` (evita multidão de clones)

Estilo-base do canal (`estilo_imagem`):
`documentary photograph, ancient Israel 1000 BC, shot on 35mm film, natural light, muted earthy colors, natural skin
texture, worn clothing, candid, slight film grain, no text`

## 2. Movimento (Wan 2.2) — UMA ação principal + micro-movimentos
- Estrutura: `[ação principal do sujeito], [micro-movimento], [ambiente], [câmera]`
- Ex.: `the boy slowly turns his head toward the valley and narrows his eyes, he blinks and breathes, wind moves his
  tunic and hair, subtle handheld camera`
- Sempre incluir algo vivo: `blinks`, `breathes`, `cloth moves in the wind`, `dust drifts`
- Câmera: `subtle handheld camera` > movimentos de grua complexos. No máximo 1 movimento de câmera por cena.
- Evitar: duas ações ao mesmo tempo, `slow motion`, verbos vagos (`moves`), mudanças de pose grandes em 3s.
- Com cfg 1 (aceleração 4 steps) o **prompt negativo é ignorado** — tudo tem que estar no positivo.

## 3. Montagem (automático no estúdio)
- `realismo: true` no roteiro → leve dessaturação, curva de filme, aberração cromática sutil e câmera na mão (micro
  tremor) em todos os clipes. Somado a grão, poeira e luz (`efeitos: true`).
- Variar a duração das cenas (2–4,5s) e alternar planos abertos, médios e closes.
