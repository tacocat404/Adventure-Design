"""로컬 판단기 — 증류 학습한 BERT 하나로 세 판단을 합친다 (AI 실험 계획 09절).

1. BERT 분류기: 문장마다 rough · threat · urgent 확률 (교사 LLM 라벨로 학습)
2. 의미 검색 kNN: 같은 BERT의 문장 벡터로 학습 문장 뱅크에서 가장 비슷한 k개를 찾아 그 라벨로 투표
3. 스태킹: [키워드 · BERT · kNN] 세 점수를 라벨마다 로지스틱 회귀로 합치고, 검증셋에서 고른 기준값으로 자른다

모델은 ml/models/judge (git에 안 올림 · ml/train.py로 만든다). 불러올 때 Linear 층을 INT8로 양자화한다.
"""
import json
from pathlib import Path

import numpy as np

LABELS = ("rough", "threat", "urgent")
K = 7
MAX_LEN = 128


class Judge:
    def __init__(self, path, quantize=True):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        path = Path(path)
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(path)
        m = AutoModelForSequenceClassification.from_pretrained(path).eval()
        if quantize:
            m = torch.ao.quantization.quantize_dynamic(m, {torch.nn.Linear}, dtype=torch.qint8)
        self.m = m
        b = np.load(path / "bank.npz", allow_pickle=False)
        self.bank, self.bank_y, self.bank_type = b["emb"].astype(np.float32), b["y"].astype(np.float32), b["type"]
        self.cfg = json.loads((path / "stack.json").read_text(encoding="utf-8"))

    def encode(self, sents):
        """BERT 한 번으로 (확률 n×3, 정규화한 문장 벡터 n×h)."""
        t = self.torch
        with t.inference_mode():
            enc = self.tok(list(sents), return_tensors="pt", padding=True, truncation=True, max_length=MAX_LEN)
            out = self.m(**enc, output_hidden_states=True)
            p = t.sigmoid(out.logits).float().numpy()
            mask = enc["attention_mask"].unsqueeze(-1).float()
            h = (out.hidden_states[-1].float() * mask).sum(1) / mask.sum(1).clamp(min=1)
            h = t.nn.functional.normalize(h, dim=-1).numpy()
        return p, h

    def knn(self, h):
        """가장 비슷한 K개 학습 문장의 라벨을 유사도로 가중 평균. (점수 n×3, 가장 가까운 문장 번호 n×K)"""
        sims = h @ self.bank.T
        idx = np.argsort(-sims, axis=1)[:, :K]
        w = np.clip(np.take_along_axis(sims, idx, 1), 0, None) + 1e-6
        return (w[..., None] * self.bank_y[idx]).sum(1) / w.sum(1, keepdims=True), idx

    def features(self, sents, kw):
        """라벨마다 [키워드, BERT, kNN] — kw는 n×3 (0/1)."""
        p, h = self.encode(sents)
        s, idx = self.knn(h)
        return np.stack([np.asarray(kw, dtype=np.float32), p, s], axis=-1), idx

    def stack(self, f):
        """f: n×3×3 → 합친 확률 n×3."""
        out = np.zeros(f.shape[:2], dtype=np.float32)
        for j, lab in enumerate(LABELS):
            c = self.cfg[lab]
            z = c["b"] + f[:, j, :] @ np.array(c["w"], dtype=np.float32)
            out[:, j] = 1 / (1 + np.exp(-z))
        return out

    def predict(self, sents, kw):
        """문장마다 {rough, threat, urgent: bool}, 합친 확률, 가장 비슷한 학습 문장 유형들."""
        if not sents:
            return [], np.zeros((0, 3)), []
        f, idx = self.features(sents, kw)
        q = self.stack(f)
        flags = [{lab: bool(q[i, j] >= self.cfg[lab]["th"]) for j, lab in enumerate(LABELS)} for i in range(len(sents))]
        types = [[str(self.bank_type[k]) for k in row] for row in idx]
        return flags, q, types
