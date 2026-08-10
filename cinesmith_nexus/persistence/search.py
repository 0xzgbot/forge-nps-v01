import math
import re
from collections import Counter
from typing import List, Dict, Any

class BM25Searcher:
    """
    A lightweight BM25 implementation for keyword-based semantic search 
    without requiring external heavy dependencies like Faiss or Elasticsearch.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_lengths = {}  # doc_id -> length
        self.avg_dl = 0        # average document length
        self.doc_counts = Counter() # term -> number of docs containing it
        self.term_freqs = {}   # doc_id -> {term: count}
        self.total_docs = 0

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenizer: lowercase and alphanumeric."""
        return re.findall(r'\w+', text.lower())

    def add_documents(self, documents: List[Dict[str, Any]]):
        """
        Expects list of dicts: [{'id': '...', 'content': '...'}, ...]
        """
        for doc in documents:
            doc_id = doc['id']
            tokens = self._tokenize(doc['content'])
            if not tokens:
                continue

            self.total_docs += 1
            self.doc_lengths[doc_id] = len(tokens)
            
            counts = Counter(tokens)
            self.term_freqs[doc_id] = counts
            
            for term in counts:
                self.doc_counts[term] += 1

        if self.total_docs > 0:
            self.avg_dl = sum(self.doc_lengths.values()) / self.total_docs

    def search(self, query: str, top_n: int = 5) -> List[Dict[str, Any]]:
        """Returns list of (doc_id, score)."""
        query_tokens = self._tokenize(query)
        if not query_tokens or self.total_docs == 0:
            return []

        scores = {}
        for token in query_tokens:
            if token not in self.doc_counts:
                continue
            
            # IDF calculation
            # idf(q) = log((N - n(q) + 0.5) / (n(q) + 0.5) + 1)
            n_q = self.doc_counts[token]
            idf = math.log(((self.total_docs - n_q + 0.5) / (n_q + 0.5)) + 1)

            for doc_id, tf in self.term_freqs.items():
                if token in tf:
                    # BM25 score component
                    # score = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (dl/avgdl)))
                    tf_val = tf[token]
                    dl = self.doc_lengths[doc_id]
                    numerator = tf_val * (self.k1 + 1)
                    denominator = tf_val + self.k1 * (1 - self.b + self.b * (dl / self.avg_dl))
                    
                    score_gain = idf * (numerator / denominator)
                    scores[doc_id] = scores.get(doc_id, 0) + score_gain

        # Sort and return top N
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return [{"id": r[0], "score": r[1]} for r in sorted_results]
