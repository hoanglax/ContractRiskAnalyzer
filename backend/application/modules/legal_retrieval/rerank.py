"""Cross-encoder rerank of a first-stage candidate pool (Qwen3-Reranker, yes/no logit method).

The reranker reads (query, chunk) together and scores P("yes") - slower than the bi-encoder but much
sharper, so it only sees the top `pool` hits of the hybrid retriever. `RerankedRetriever` wraps any
Retriever, so it drops into eval / bench unchanged.
"""
import json
import os
import urllib.request
from pathlib import Path

from application.modules.legal_retrieval.retriever import Hit

MODEL = Path(os.environ.get("RERANK_MODEL", Path.home() / "models" / "qwen3-reranker-0.6b"))
INSTRUCT = "Given a question about a Vietnamese contract, retrieve the statute passage that answers it"
PREFIX = ("<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the "
          "Instruct provided. Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n")
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


class Reranker:
    def __init__(self, model_path: str | Path = MODEL, max_len: int = 1024, bf16: bool = False):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch, self.max_len = torch, max_len
        self.tok = AutoTokenizer.from_pretrained(str(model_path), padding_side="left")
        self.model = AutoModelForCausalLM.from_pretrained(
            str(model_path), dtype=torch.bfloat16 if bf16 else torch.float32).eval()
        self.yes = self.tok.convert_tokens_to_ids("yes")
        self.no = self.tok.convert_tokens_to_ids("no")

    def score(self, query: str, docs: list[str], batch: int = 8) -> list[float]:
        torch = self.torch
        texts = [f"{PREFIX}<Instruct>: {INSTRUCT}\n<Query>: {query}\n<Document>: {d}{SUFFIX}" for d in docs]
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = [0.0] * len(texts)
        with torch.inference_mode():
            for b in range(0, len(order), batch):
                idx = order[b:b + batch]
                enc = self.tok([texts[i] for i in idx], padding=True, truncation=True,
                               max_length=self.max_len, return_tensors="pt")
                logits = self.model(**enc).logits[:, -1, :]
                two = torch.stack([logits[:, self.no], logits[:, self.yes]], dim=1)
                p = torch.log_softmax(two.float(), dim=1)[:, 1].exp()
                for j, i in enumerate(idx):
                    out[i] = float(p[j])
        return out


class ServerReranker:
    """Qwen3-Reranker behind a llama-server /v1/rerank endpoint (see the old repo's scripts/rerank-server.sh)."""

    def __init__(self, url: str = os.environ.get("RERANK_URL", "http://127.0.0.1:8081/v1/rerank")):
        self.url = url

    def score(self, query: str, docs: list[str]) -> list[float]:
        req = urllib.request.Request(self.url, json.dumps({"query": query, "documents": docs}).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            res = json.load(r)["results"]
        out = [0.0] * len(docs)
        for o in res:
            out[int(o["index"])] = float(o["relevance_score"])
        return out


class RerankedRetriever:
    def __init__(self, base, reranker: Reranker | None = None, pool: int = 30):
        self.base, self.reranker, self.pool = base, reranker or Reranker(), pool

    def search(self, query: str, k: int = 5, law: str | None = None) -> list[Hit]:
        cands = self.base.search(query, max(self.pool, k), law)
        scores = self.reranker.score(query, [h.text for h in cands])
        ranked = sorted(zip(scores, range(len(cands))), key=lambda t: (-t[0], t[1]))
        out = []
        for s, i in ranked[:k]:
            h = cands[i]
            out.append(Hit(h.chunk_id, h.article_id, h.law, h.dieu_no, h.ref, s, h.text))
        return out
