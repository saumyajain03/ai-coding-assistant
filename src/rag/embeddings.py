"""
Local Privacy-First Embeddings
Manages local embedding generation on CPU with fast local ONNX runtime support
and graceful fallback to SentenceTransformers.
Enforces strict offline mode and air-gapped execution.
"""

import os
from pathlib import Path
from typing import Any

from src.config import get_settings


class LocalEmbeddingEngine:
    def __init__(self):
        self.settings = get_settings()
        self.model_name = self.settings.EMBEDDING_MODEL_NAME
        self.device = self.settings.EMBEDDING_DEVICE
        self._st_model: Any = None
        self._onnx_session: Any = None
        self._tokenizer: Any = None
        self._init_fast_onnx()

    def _init_fast_onnx(self) -> None:
        """
        Attempts to initialize in-process ONNX runtime for all-MiniLM-L6-v2.
        Loads in ~10ms and avoids PyTorch initialization overhead on CPU.
        """
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            model_dir = Path(os.path.expanduser("~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx"))
            model_path = model_dir / "model.onnx"
            tok_path = model_dir / "tokenizer.json"

            if model_path.exists() and tok_path.exists():
                tok = Tokenizer.from_file(str(tok_path))
                tok.enable_padding(length=128)
                tok.enable_truncation(max_length=128)
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 1
                opts.inter_op_num_threads = 1
                self._onnx_session = ort.InferenceSession(str(model_path), opts)
                self._tokenizer = tok
        except Exception:
            self._onnx_session = None
            self._tokenizer = None

    def get_model(self) -> Any:
        """
        Loads SentenceTransformer locally on CPU as fallback.
        """
        if self._st_model is None:
            from sentence_transformers import SentenceTransformer

            # Offline check
            if self.settings.OFFLINE_MODE:
                self._st_model = SentenceTransformer(
                    self.model_name,
                    device=self.device,
                    local_files_only=True,
                )
            else:
                self._st_model = SentenceTransformer(
                    self.model_name,
                    device=self.device,
                )
        return self._st_model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Computes normalized dense embeddings for a list of text strings.
        Uses fast ONNX if available, else SentenceTransformers.
        """
        if not texts:
            return []

        if self._onnx_session is not None and self._tokenizer is not None:
            import numpy as np

            results: list[list[float]] = []
            for t in texts:
                enc = self._tokenizer.encode(t)
                inputs = {
                    "input_ids": np.array([enc.ids], dtype=np.int64),
                    "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
                    "token_type_ids": np.array([enc.type_ids], dtype=np.int64),
                }
                out = self._onnx_session.run(None, inputs)[0]
                mask = np.expand_dims(inputs["attention_mask"], -1)
                summed = np.sum(out * mask, axis=1)
                counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
                mean_pooled = summed / counts
                norm = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
                normed = mean_pooled / np.clip(norm, a_min=1e-9, a_max=None)
                results.append(normed[0].tolist())
            return results

        model = self.get_model()
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        """
        Computes dense embedding for a single query string.
        """
        res = self.embed_texts([query])
        return res[0] if res else []


_embedding_engine_instance: LocalEmbeddingEngine | None = None


def get_embedding_engine() -> LocalEmbeddingEngine:
    global _embedding_engine_instance
    if _embedding_engine_instance is None:
        _embedding_engine_instance = LocalEmbeddingEngine()
    return _embedding_engine_instance
