# Third-party notices for optional voice packs

## Smooth German/English JARVIS v2 voice

The preferred bilingual pack uses the Q4 German and English
[NeuTTS Nano](https://github.com/neuphonic/neutts) backbones with the
NeuCodec INT8 ONNX decoder. The model files are distributed under the NeuTTS
Open License v1.0; a complete copy is included in the pack. The compact
runtime uses llama.cpp, ONNX Runtime, Phonemizer, and eSpeak NG, whose
distribution license files are copied into the pack.

JARVIS uses a modified, inference-only version of the NeuTTS 1.4.1 GGUF/ONNX
path. It loads each language backbone only when first needed, then keeps the
two compact Q4 backbones cached during an active bilingual conversation. It
excludes the large reference encoder, PyTorch, Transformers, and the optional
PyTorch Perth watermarker. The two numerical profiles are derived from the
user's JARVIS v2 references; the source recordings are not included.

## Fast German/English cloned voice

The low-latency Apple Silicon pack uses
[MOSS-TTS-Nano](https://huggingface.co/OpenMOSS-Team/MOSS-TTS-Nano-100M)
through [MLX-Audio](https://github.com/Blaizzy/mlx-audio). The model is
published under Apache-2.0 and the MLX-Audio runtime under MIT. The build
copies the license files shipped by the installed distributions into the
pack.

The compact prompt-token profile is derived from the user-provided JARVIS v2
reference recording. The original recording is not placed inside the pack.

## Chatterbox studio voice

The higher-resource studio pack is built from the official
[ResembleAI Chatterbox](https://github.com/resemble-ai/chatterbox) implementation
and the `ResembleAI/chatterbox-turbo` model. Both are distributed under the MIT
license. Chatterbox applies ResembleAI's Perth implicit watermark to generated
audio.

The build script copies the license files shipped by the installed Python
distributions into the pack's `licenses/` directory. This covers the inference
runtime and its packaged dependencies, including PyTorch, Transformers,
Diffusers, Librosa, and Perth.

Its JARVIS voice profile is also a derived numerical condition profile; its
source recording is not placed inside the voice pack.
