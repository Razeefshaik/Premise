"""Serialized ingestion and assessment pipeline, with graph-backed poll cursors."""
from __future__ import annotations

import asyncio
import logging
from ..ingest.run import ingest
from ..reasoning.assess import assess, graph_ready, now_ms
from ..reasoning.intake import overlay_from_files
from ..reasoning.models import AssessmentResult, Reason
from ..graph.client import GraphUnavailable
from .actions import Executor, StaleAssessment
from .store import Store

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, client, github, gitrepo, settings):
        self.client, self.github, self.git, self.settings = client, github, gitrepo, settings
        self.store = Store(client)
        self.executor = Executor(client, github, settings.public_base_url, settings.auto_fix_pr)
        self._sync_retry_at = 0
        self._sync_failures = 0

    def sync_main(self):
        sha = self.git.main()
        ready, _, _ = graph_ready(self.client)
        state = self.client.named("graph_state") if ready else []
        if not state or state[0]["main_sha"] != sha:
            ingest(self.client, self.git.root, sha, f"https://github.com/{self.github.repo}")
        return sha

    def assess_pr(self, number, execute=False):
        pr = self.github.pull(number)
        try:
            ready, _, why = graph_ready(self.client)
            if not ready:
                raise GraphUnavailable(why)
            if execute:
                self.github.status(pr["head"]["sha"], "pending", "Assessing decision guarantees")
            state = self.client.named("graph_state")[0]
            files = self.git.pr_files(number, pr["head"]["sha"], state["main_sha"])
            issues = []
            changes, paths, model = overlay_from_files(self.client, files.head, base_files=files.base, issues=issues)
            result = assess(self.client, changes, changed_paths=paths, model_change=model,
                pr=f"pr:{number}", head_sha=pr["head"]["sha"], since_days=self.settings.since_days)
            if issues and result.verdict != "ERROR":
                result.reasons = issues + [r for r in result.reasons if r.code not in {"R_ALL_HOLD", "R_NO_TRACKED_FACTS"}]
                if result.verdict != "BLOCKED":
                    result.verdict = "NEEDS_REVIEW"
                # Incomplete intake cannot establish a complete remedy.
                result.fixes = []
            if result.verdict != "ERROR" and not issues:
                from ..agent.fix_agent import augment_fixes
                augment_fixes(self.client, result, self.settings)
        except Exception as exc:
            if not isinstance(exc, GraphUnavailable):
                log.exception("Unexpected assessment failure for PR #%s", number)
            result = AssessmentResult(pr=f"pr:{number}", head_sha=pr["head"]["sha"], verdict="ERROR",
                reasons=[Reason(code="R_UNAVAILABLE" if isinstance(exc, GraphUnavailable) else "R_INTERNAL_ERROR",
                    detail=f"Assessment unavailable ({type(exc).__name__})")])
        if execute:
            self.executor.execute(result, pr)
        elif result.verdict != "ERROR":
            self.store.save(result, pr)
        return result

    def once(self):
        if now_ms() < self._sync_retry_at:
            return []
        try:
            self.sync_main()
        except Exception:
            log.exception("Main synchronization failed")
            self._sync_failures += 1
            self._sync_retry_at = now_ms() + self.retry_delay(self._sync_failures)
            # Without a ready graph, only current-head error statuses are permitted.
            prs, _ = self.github.open_pulls()
            for pr in prs or []:
                latest = self.github.pull(pr["number"])
                if latest["state"] == "open" and latest["head"]["sha"] == pr["head"]["sha"]:
                    self.github.status(pr["head"]["sha"], "error", "Assessment unavailable: ingestion or graph failed")
            raise
        self._sync_failures = self._sync_retry_at = 0
        self.executor.reconcile()
        cursor = self.store.cursor()
        rev = self.client.named("graph_state")[0]["rev"]
        # Main revisions invalidate all PR cursors, including when ETag says unchanged.
        previous_errors = cursor.get("errors", {}) if cursor.get("rev") == rev else {}
        prs, etag = self.github.open_pulls(cursor.get("etag") if cursor.get("rev") == rev and not previous_errors else None)
        if prs is None:
            return []
        old = cursor.get("prs", {}) if cursor.get("rev") == rev else {}
        done, errors, results = {}, {}, []
        for pr in prs:
            key = str(pr["number"])
            if old.get(key) == pr["head"]["sha"]:
                done[key] = old[key]
                continue
            previous = previous_errors.get(key, {})
            if previous.get("head_sha") != pr["head"]["sha"]:
                previous = {}
            if previous.get("retry_at", 0) > now_ms():
                errors[key] = previous
                continue
            try:
                result = self.assess_pr(pr["number"], execute=True)
                results.append(result)
                if result.verdict != "ERROR":
                    done[key] = result.head_sha
                else:
                    attempts = previous.get("attempts", 0) + 1
                    errors[key] = {"head_sha": result.head_sha, "attempts": attempts,
                                   "retry_at": now_ms() + self.retry_delay(attempts)}
            except (StaleAssessment, GraphUnavailable):
                continue
        # An incomplete poll must not retain an ETag that would suppress retries.
        self.store.set_cursor({"rev": rev, "etag": etag if len(done) == len(prs) else None, "prs": done, "errors": errors})
        return results

    @staticmethod
    def retry_delay(attempts):
        return min(60_000 * 2 ** min(attempts - 1, 4), 900_000)


async def poll(pipeline):
    while True:
        try:
            await asyncio.to_thread(pipeline.once)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Poll failed (%s); retrying with backoff", type(exc).__name__)
        await asyncio.sleep(pipeline.settings.poll_seconds)
