#!/bin/bash
# Roda no pod ao ligar (injetado via env BOOT_B64). Idempotente: só baixa o que falta.
M=/workspace/runpod-slim/ComfyUI/models
CN=/workspace/runpod-slim/ComfyUI/custom_nodes
if [ "$1" = "pre" ]; then
  # nós extras (antes do ComfyUI subir): interpolação RIFE
  if [ -d "$CN" ] && [ ! -d "$CN/ComfyUI-Frame-Interpolation" ]; then
    git clone -q --depth 1 https://github.com/Fannovel16/ComfyUI-Frame-Interpolation "$CN/ComfyUI-Frame-Interpolation" && echo "ok node RIFE"
    /workspace/runpod-slim/ComfyUI/.venv-cu128/bin/pip install -q einops opencv-contrib-python-headless kornia scipy >/dev/null 2>&1 && echo "ok deps RIFE"
  fi
  # atualização do ComfyUI (nós nativos de 3D exigem versão nova). Idempotente, com backup da versão anterior.
  CV=v0.42.5; CU=/workspace/runpod-slim/ComfyUI
  if [ -d "$CU" ] && ! grep -q "${CV#v}" "$CU/comfyui_version.py" 2>/dev/null; then
    echo "atualizando ComfyUI para $CV"
    [ -d /workspace/_comfy_bak ] || rsync -a --exclude=/models --exclude=/custom_nodes --exclude='/.venv*' \
        --exclude=/input --exclude=/output --exclude=/user "$CU/" /workspace/_comfy_bak/
    rm -rf /tmp/cu && mkdir -p /tmp/cu && curl -sSL https://codeload.github.com/comfyanonymous/ComfyUI/tar.gz/refs/tags/$CV \
        | tar xz -C /tmp/cu --strip-components=1 && \
    rsync -a --delete --exclude=/models --exclude=/custom_nodes --exclude='/.venv*' --exclude=/input --exclude=/output \
        --exclude=/user --exclude=/.runpod-bundle-version --exclude=/extra_model_paths.yaml /tmp/cu/ "$CU/" && \
    "$CU/.venv-cu128/bin/pip" install -q -r "$CU/requirements.txt" >/tmp/pip_cu.log 2>&1 && echo "ok ComfyUI $CV" \
        || { echo "ERRO update ComfyUI"; tail -5 /tmp/pip_cu.log; }
  fi
  exit 0
fi
for i in $(seq 1 120); do [ -d "$M" ] && break; sleep 5; done
mkdir -p $M/checkpoints $M/diffusion_models $M/text_encoders $M/vae $M/loras
T=/workspace/_downloads; mkdir -p $T
# baixa fora da pasta de modelos e só move no fim — o ComfyUI nunca vê arquivo pela metade
command -v aria2c >/dev/null || (apt-get update -qq && apt-get install -y -qq aria2 >/dev/null 2>&1)
# aria2c com 16 conexões: ~300 MB/s vs ~5 MB/s do wget numa conexão só
get() { f=$(basename $2); [ -s "$1/$f" ] && echo "ok $f" && return; echo "baixando $f"
  if command -v aria2c >/dev/null; then aria2c -q -c -x16 -s16 -k20M -d "$T" -o "$f" "$2"
  else wget -q -c -O "$T/$f" "$2"; fi && mv "$T/$f" "$1/$f" && echo "ok $f" || echo "ERRO $f"; }
HF=https://huggingface.co
W=$HF/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files
# Wan 2.2 I2V (vídeo)
get $M/diffusion_models $W/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors &
get $M/diffusion_models $W/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors &
get $M/text_encoders    $W/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors &
get $M/vae              $W/vae/wan_2.1_vae.safetensors &
get $M/loras $HF/rzgar/Wan2.2_I2V_LightX2V_Slow-Mo_Fix/resolve/main/wan2.2_i2v_lightx2v_motion_fix_high.safetensors &
get $M/loras $HF/rzgar/Wan2.2_I2V_LightX2V_Slow-Mo_Fix/resolve/main/wan2.2_i2v_lightx2v_motion_fix_low.safetensors &
# Flux schnell (fichas de personagem e cenas sem personagem)
get $M/checkpoints $HF/Comfy-Org/flux1-schnell/resolve/main/flux1-schnell-fp8.safetensors &
# Qwen-Image-Edit 2511 (cenas com personagem fixo, 4 steps embutidos)
get $M/diffusion_models $HF/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/qwen_image_edit_2511_fp8_e4m3fn_scaled_lightning_comfyui_4steps_v1.0.safetensors &
get $M/text_encoders $HF/Comfy-Org/HunyuanVideo_1.5_repackaged/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors &
get $M/vae $HF/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors &
# 3D: Pixal3D / TRELLIS.2 (imagem -> malha texturizada) + remoção de fundo + MoGe (FOV)
P3=$HF/Comfy-Org/Pixal3D/resolve/main
mkdir -p $M/clip_vision $M/geometry_estimation $M/background_removal
get $M/diffusion_models $P3/diffusion_models/pixal3d_int8_convrot.safetensors &
get $M/diffusion_models $HF/Comfy-Org/TRELLIS.2/resolve/main/diffusion_models/trellis_2_int8_convrot.safetensors &
get $M/vae $P3/vae/trellis_2_shape_vae_bf16.safetensors &
get $M/vae $P3/vae/trellis_2_texture_vae_bf16.safetensors &
get $M/clip_vision $P3/clip_vision/dino_v3_L_naf_fp32.safetensors &
get $M/geometry_estimation $HF/Comfy-Org/MoGe/resolve/main/geometry_estimation/moge_2_vitl_normal_fp16.safetensors &
get $M/background_removal $HF/Comfy-Org/BiRefNet/resolve/main/background_removal/birefnet.safetensors &
wait
df -h /workspace | tail -1
echo "BOOT_DONE"
