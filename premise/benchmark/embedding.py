"""Pinned MiniLM checkpoint, CPU ONNX inference, exact-text embedding cache."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


class Embedder:
    def __init__(self, download=False, cache=None):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        self.spec = json.loads((ROOT / 'bench/model.json').read_text())
        self.cache = Path(cache or ROOT / 'bench/cache')
        model = self.cache / self.spec['revision']
        model.mkdir(parents=True, exist_ok=True)
        for filename in ('tokenizer.json', 'onnx/model.onnx'):
            path = model / filename
            if not path.exists():
                if not download:
                    raise ValueError('Embedding model not cached. Run premise bench run --download-model once.')
                path.parent.mkdir(parents=True, exist_ok=True)
                url = f"https://huggingface.co/{self.spec['model']}/resolve/{self.spec['revision']}/{filename}?download=true"
                temp = path.with_suffix('.part')
                with urllib.request.urlopen(url, timeout=120) as source, temp.open('wb') as dest:
                    while chunk := source.read(1024 * 1024):
                        dest.write(chunk)
                temp.replace(path)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(str(model / 'onnx/model.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
        self.tokenizer = Tokenizer.from_file(str(model / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding()

    def encode(self, text):
        key = hashlib.sha256((self.spec['revision'] + '\0' + text).encode()).hexdigest()
        path = self.cache / (key + '.json')
        if path.exists():
            return json.loads(path.read_text())
        tokens = self.tokenizer.encode(text)
        feed = {'input_ids': self.np.array([tokens.ids], dtype='int64'),
                'attention_mask': self.np.array([tokens.attention_mask], dtype='int64'),
                'token_type_ids': self.np.array([tokens.type_ids], dtype='int64')}
        feed = {n.name: feed[n.name] for n in self.session.get_inputs()}
        output = self.session.run(None, feed)[0]
        mask = feed['attention_mask'][..., None]
        vector = (output * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1e-9)
        vector /= self.np.linalg.norm(vector, axis=1, keepdims=True).clip(min=1e-9)
        result = vector[0].tolist()
        if len(result) != 384 or not self.np.isfinite(result).all():
            raise ValueError('Invalid embedding')
        path.write_text(json.dumps(result), encoding='utf-8')
        return result
