"""
Local Privacy-First Embeddings
Manages local SentenceTransformers embedding generation on CPU.
Enforces strict offline mode and air-gapped execution once weights are downloaded.
"""

from typing import Any

from src.config import get_settings


class LocalEmbeddingEngine:
    def __init__(self):
        self.settings = get_settings()
        self.model_name = self.settings.EMBEDDING_MODEL_NAME
        self.device = self.settings.EMBEDDING_DEVICE
        self._model: Any = None

    def get_model(self) -> Any:
        """
        Loads SentenceTransformer locally on CPU.
        """
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            # Offline check
            if self.settings.OFFLINE_MODE:
                # Disallow network downloads
                self._model = SentenceTransformer(
                    self.model_name,
                    device=self.device,
                    local_files_only=True,
                )
            else:
                self._model = SentenceTransformer(
                    self.model_name,
                    device=self.device,
                )
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Computes normalized dense embeddings for a list of text strings.
        """
        if not texts:
            return []
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
