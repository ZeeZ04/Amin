"""Publish Amin's on-device builds to Hugging Face, where the app downloads them.

    uv run hf auth login                      # once, with a write token from your HF account
    uv run python scripts/publish_model.py <org> edge-2-m46 edge-2-q6 edge-2-q8

Each build goes to <org>/<build> with a model card. The app lists them through
the Hugging Face API (apple/Sources/Kit/ModelSource.swift) when AMIN_HF_MODEL_ORG
is set to <org>. The weights are edge-2 (Gemma 4 E4B, Apache-2.0, SFT then DPO;
docs/EXPERIMENTS.md E35-E39); training data and its licences are in docs/TRAINING.md.
Publishing makes the weights public: check that document before the first upload.
"""

from __future__ import annotations

import sys
from pathlib import Path

MODELS = Path(__file__).resolve().parent.parent / "data" / "models"

PURPOSE = {
    "edge-2-m46": ("iPhone", "mixed 4/6-bit, 4.1 GB", "E39"),
    "edge-2-q6": ("iPad and Mac", "6-bit, 5.7 GB", "E38"),
    "edge-2-q8": ("Mac", "8-bit, 7.4 GB", "E38"),
}

CARD = """---
license: apache-2.0
base_model: google/gemma-4-E4B-it
library_name: mlx
language: [en, ar, ml]
tags: [mlx, on-device, rag, amin]
---

# Amin {name}

Amin's own model for the {device}: Gemma 4 E4B fine-tuned (SFT, then DPO) to answer
only from the passages it is given, cite them as [S1], [S2], and say so plainly when
they do not hold the answer. English, Arabic and Malayalam. {quant}.

Built for the Amin app, which runs it on the device with MLX Swift: questions and
documents never leave the device. Evaluation: Amin's docs/EXPERIMENTS.md {exp}.

Licence: Apache-2.0, as the base model.
"""


def publish(org: str, name: str) -> None:
    from huggingface_hub import HfApi

    folder = MODELS / name
    if not (folder / "config.json").exists():
        raise SystemExit(f"{folder} has no config.json; build it first")
    device, quant, exp = PURPOSE[name]
    (folder / "README.md").write_text(CARD.format(name=name, device=device, quant=quant, exp=exp), encoding="utf-8")
    api = HfApi()
    repo = f"{org}/{name}"
    api.create_repo(repo, repo_type="model", exist_ok=True)
    api.upload_folder(repo_id=repo, folder_path=folder, commit_message=f"Amin {name}",
                      allow_patterns=["*.safetensors", "*.json", "*.jinja", "tokenizer.model", "README.md"])
    print(f"published https://huggingface.co/{repo}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    org, *names = sys.argv[1:]
    for n in names:
        if n not in PURPOSE:
            raise SystemExit(f"unknown build {n}; one of {', '.join(PURPOSE)}")
        publish(org, n)
