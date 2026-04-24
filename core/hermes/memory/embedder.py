"""
Embedding backends for episodic memory retrieval.

Provides a pluggable interface so Hermes can use:
  • Ollama (local neural embeddings) — recommended for hackathon demos
  • Numpy TF-IDF (zero-dependency fallback) — works anywhere
  • sentence-transformers, OpenAI, etc. — easy to add
"""

import json
import re
import math
import os
from abc import ABC, abstractmethod
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np


class BaseEmbedder(ABC):
    """Pluggable embedding interface."""

    @abstractmethod
    def embed(self, text: str) -> np.ndarray:
        """Return a 1-D numpy vector for the given text."""
        pass

    def similarity(self, vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        dot = np.dot(vec_a, vec_b)
        norm = np.linalg.norm(vec_a) * np.linalg.norm(vec_b)
        return float(dot / norm) if norm > 1e-9 else 0.0


class KimiEmbedder(BaseEmbedder):
    """
    Moonshot / Kimi embeddings via the OpenAI-compatible API.
    Endpoint: https://api.moonshot.cn/v1/embeddings
    This is the recommended backend for the Kimi hackathon track.
    """

    def __init__(
        self,
        model: str = "moonshot-v1-embedding",
        api_key: Optional[str] = None,
        base_url: str = "https://api.moonshot.cn/v1",
        cache_size: int = 512,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("KIMI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self._cache: Dict[str, np.ndarray] = {}
        self._cache_size = cache_size

    def embed(self, text: str) -> np.ndarray:
        if not self.api_key or self.api_key == "dummy_key":
            return np.zeros(1, dtype=np.float32)  # signal unavailable

        if text in self._cache:
            return self._cache[text]

        try:
            import urllib.request
            payload = json.dumps({"model": self.model, "input": text}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/embeddings",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                vec = np.array(data["data"][0]["embedding"], dtype=np.float32)
        except Exception:
            vec = np.zeros(1, dtype=np.float32)

        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[text] = vec
        return vec

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key != "dummy_key")


class LMStudioEmbedder(BaseEmbedder):
    """
    Local neural embeddings via LM Studio's OpenAI-compatible server.
    LM Studio loads any embedding model (e.g. nomic-embed-text, all-minilm, bge-small-en).
    Endpoint: configured via LMSTUDIO_HOST env var (default: http://localhost:1234/v1)
    """

    def __init__(
        self,
        model: str = "text-embedding-nomic-embed-text-v1.5",
        base_url: str = "http://localhost:1234/v1",
        cache_size: int = 512,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._cache: Dict[str, np.ndarray] = {}
        self._cache_size = cache_size

    def embed(self, text: str) -> np.ndarray:
        if text in self._cache:
            return self._cache[text]

        try:
            import urllib.request
            payload = json.dumps({"model": self.model, "input": text}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                vec = np.array(data["data"][0]["embedding"], dtype=np.float32)
        except Exception:
            # Graceful degradation: return a zero vector so the caller
            # can fall back to keyword search or another backend.
            vec = np.zeros(1, dtype=np.float32)

        # Simple LRU-style cache eviction
        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[text] = vec
        return vec

    @property
    def is_available(self) -> bool:
        """Check if LM Studio server is reachable."""
        try:
            import urllib.request
            req = urllib.request.Request(f"{self.base_url}/models", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False


class NumpyTfidfEmbedder(BaseEmbedder):
    """
    Zero-dependency TF-IDF + cosine similarity fallback.
    Surprisingly effective for structured production logs.
    """

    def __init__(self, max_features: int = 2048):
        self.max_features = max_features
        self._vocab: Dict[str, int] = {}
        self._idf: Optional[np.ndarray] = None
        self._doc_count = 0

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    def _fit_if_needed(self, corpus: List[str]):
        """Rebuild vocab/IDF from corpus if it has grown significantly."""
        if self._idf is not None and abs(len(corpus) - self._doc_count) < 5:
            return

        self._doc_count = len(corpus)
        token_lists = [self._tokenize(d) for d in corpus]
        all_tokens = [t for tokens in token_lists for t in tokens]

        # Keep top-N most frequent tokens as vocab
        freq = Counter(all_tokens)
        top = freq.most_common(self.max_features)
        self._vocab = {term: idx for idx, (term, _) in enumerate(top)}

        # Compute IDF
        idf = np.zeros(len(self._vocab), dtype=np.float32)
        for term, idx in self._vocab.items():
            doc_freq = sum(1 for tokens in token_lists if term in tokens)
            idf[idx] = math.log((len(corpus) + 1) / (doc_freq + 1)) + 1.0
        self._idf = idf

    def embed(self, text: str) -> np.ndarray:
        tokens = self._tokenize(text)
        vec = np.zeros(len(self._vocab), dtype=np.float32)
        tf = Counter(tokens)
        for term, count in tf.items():
            if term in self._vocab:
                idx = self._vocab[term]
                vec[idx] = count * self._idf[idx]
        # L2-normalize
        norm = np.linalg.norm(vec)
        if norm > 1e-9:
            vec /= norm
        return vec

    def fit(self, corpus: List[str]):
        """Explicitly fit the TF-IDF model on a corpus."""
        self._fit_if_needed(corpus)


class HybridEmbedder(BaseEmbedder):
    """
    Priority chain for hackathon demos:
      1. Kimi (Moonshot) embeddings — on-brand, cloud-quality
      2. LM Studio local — any loaded embedding model, offline-capable
      3. Numpy TF-IDF — zero-dependency fallback
    """

    def __init__(self):
        self.kimi = KimiEmbedder()
        self.lmstudio = LMStudioEmbedder()
        self.fallback = NumpyTfidfEmbedder()
        self._backend_name = "unknown"
        self._fallback_corpus: List[str] = []

    def embed(self, text: str) -> np.ndarray:
        # 1. Try Kimi first
        if self.kimi.is_available:
            vec = self.kimi.embed(text)
            if np.linalg.norm(vec) > 1e-9:
                self._backend_name = "kimi"
                return vec

        # 2. Try LM Studio local
        if self.lmstudio.is_available:
            vec = self.lmstudio.embed(text)
            if np.linalg.norm(vec) > 1e-9:
                self._backend_name = "lmstudio"
                return vec

        # 3. Fallback to TF-IDF
        self._backend_name = "tfidf"
        if self._fallback_corpus:
            self.fallback.fit(self._fallback_corpus)
        return self.fallback.embed(text)

    @property
    def active_backend(self) -> str:
        return self._backend_name

    def register_corpus(self, corpus: List[str]):
        """Provide the fallback embedder with documents to build TF-IDF vocab."""
        self._fallback_corpus = corpus
        if not self.kimi.is_available and not self.lmstudio.is_available:
            self.fallback.fit(corpus)
