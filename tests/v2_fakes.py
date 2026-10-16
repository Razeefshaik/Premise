"""Deterministic model fixture; tests must never construct a real adapter."""
from copy import deepcopy


class FakeAdapter:
    model = "fixture-model"

    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = []

    def structured(self, system, payload):
        self.calls.append({"system": system, "payload": payload})
        if not self.responses:
            raise AssertionError("unexpected model call; no fixture response")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return deepcopy(result)
