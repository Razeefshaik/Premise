"""Deterministic model responses for tests and recorded evaluations; no network."""
from copy import deepcopy
import hashlib


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class FakeAdapter:
    model = "fixture-model"

    def __init__(self, responses=(), requests=None, model=None):
        self.responses = list(responses)
        self.requests = list(requests) if requests is not None else None
        self.calls = []
        if model:
            self.model = model

    def structured(self, system, payload):
        self.calls.append({"system": system, "payload": payload})
        if self.requests is not None:
            if not self.requests:
                raise AssertionError("unexpected recorded model call")
            request = self.requests.pop(0)
            if request["system_hash"] != digest(system) or request["payload_hash"] != digest(payload):
                raise AssertionError("recording no longer matches the prompt or source")
        if not self.responses:
            raise AssertionError("unexpected model call; no fixture response")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return deepcopy(result)
