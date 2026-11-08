"""Download a pinned ONNX graph/tokenizer, never Python model code or user data."""
import json
import os
from pathlib import Path
from huggingface_hub import snapshot_download

REPO = Path(__file__).resolve().parents[1]
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
path = snapshot_download('onnx-community/Qwen2.5-1.5B-Instruct', revision='d54957e3af1be04546436e874a60fe386041b244',
    allow_patterns=['onnx/model_q4.onnx', 'config.json', 'generation_config.json', 'tokenizer.json', 'tokenizer_config.json', 'README.md'],
    cache_dir=REPO / 'state/models/chat', token=False)
print(json.dumps({'model_path': path, 'downloaded': True}))
