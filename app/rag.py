from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RAGHit:
    source: str
    score: float
    excerpt: str


class StandardsRAG:
    """Простой локальный retrieval по легально загруженным документам/выжимкам."""

    def __init__(self, docs_dir: Path) -> None:
        self.docs_dir = docs_dir
        self.docs_dir.mkdir(parents=True, exist_ok=True)

    def _load_docs(self) -> list[tuple[str, str]]:
        docs: list[tuple[str, str]] = []
        for path in sorted(self.docs_dir.glob("*.md")) + sorted(self.docs_dir.glob("*.txt")):
            docs.append((path.name, path.read_text(encoding="utf-8", errors="ignore")))
        for path in sorted(self.docs_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                docs.append((path.name, json.dumps(payload, ensure_ascii=False)))
            except Exception:  # noqa: BLE001
                continue
        return docs

    def retrieve(self, query: str, top_k: int = 5) -> list[RAGHit]:
        docs = self._load_docs()
        if not docs:
            return []

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
            from sklearn.metrics.pairwise import cosine_similarity  # type: ignore

            vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
            corpus = [doc_text for _, doc_text in docs]
            tfidf = vectorizer.fit_transform(corpus + [query])
            doc_vecs = tfidf[:-1]
            query_vec = tfidf[-1]
            sims = cosine_similarity(doc_vecs, query_vec).ravel()

            indexed = sorted(enumerate(sims.tolist()), key=lambda x: x[1], reverse=True)[:top_k]
            hits: list[RAGHit] = []
            for idx, score in indexed:
                name, text = docs[idx]
                excerpt = text[:400].replace("\n", " ")
                hits.append(RAGHit(source=name, score=float(score), excerpt=excerpt))
            return hits
        except Exception:
            # fallback: keyword overlap
            q_tokens = set(query.lower().split())
            scored: list[tuple[int, float]] = []
            for i, (_, txt) in enumerate(docs):
                t_tokens = set(txt.lower().split())
                overlap = len(q_tokens.intersection(t_tokens))
                scored.append((i, float(overlap)))
            scored.sort(key=lambda x: x[1], reverse=True)

            hits = []
            for idx, score in scored[:top_k]:
                name, text = docs[idx]
                hits.append(RAGHit(source=name, score=score, excerpt=text[:400].replace("\n", " ")))
            return hits


def hits_as_dict(hits: list[RAGHit]) -> list[dict[str, str | float]]:
    return [{"source": h.source, "score": h.score, "excerpt": h.excerpt} for h in hits]
