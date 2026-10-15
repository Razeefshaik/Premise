"""Serialized ingestion and assessment pipeline, with graph-backed poll cursors."""
from __future__ import annotations

import asyncio
import logging
from ..ingest.run import ingest
from ..reasoning.assess import assess, graph_ready
from ..reasoning.intake import overlay_from_files
from ..reasoning.models import AssessmentResult, Reason
from .actions import Executor, StaleAssessment
from .store import Store

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, client, github, gitrepo, settings):
        self.client, self.github, self.git, self.settings = client, github, gitrepo, settings
        self.store = Store(client)
        self.executor = Executor(client, github, settings.public_base_url, settings.auto_fix_pr)

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
                raise RuntimeError(why)
            if execute:
                self.github.status(pr["head"]["sha"], "pending", "Assessing decision guarantees")
            state = self.client.named("graph_state")[0]
            files = self.git.pr_files(number, pr["head"]["sha"], state["main_sha"])
            changes, paths, model = overlay_from_files(self.client, files)
            result = assess(self.client, changes, changed_paths=paths, model_change=model,
                pr=f"pr:{number}", head_sha=pr["head"]["sha"], since_days=self.settings.since_days)
            if result.verdict != "ERROR":
                from ..agent.fix_agent import augment_fixes
                augment_fixes(self.client, result, self.settings)
        except Exception as exc:
            result = AssessmentResult(pr=f"pr:{number}", head_sha=pr["head"]["sha"], verdict="ERROR",
                reasons=[Reason(code="R_UNAVAILABLE", detail=f"Assessment unavailable ({type(exc).__name__})")])
        if execute:
            self.executor.execute(result, pr)
        elif result.verdict != "ERROR":
            self.store.save(result, pr)
        return result

    def once(self):
        self.sync_main()
        self.executor.reconcile()
        cursor = self.store.cursor()
        rev = self.client.named("graph_state")[0]["rev"]
        # Main revisions invalidate all PR cursors, including when ETag says unchanged.
        prs, etag = self.github.open_pulls(cursor.get("etag") if cursor.get("rev") == rev else None)
        if prs is None:
            return []
        old = cursor.get("prs", {}) if cursor.get("rev") == rev else {}
        done, results = {}, []
        for pr in prs:
            key = str(pr["number"])
            if old.get(key) == pr["head"]["sha"]:
                done[key] = old[key]
                continue
            try:
                result = self.assess_pr(pr["number"], execute=True)
                results.append(result)
                if result.verdict != "ERROR":
                    done[key] = result.head_sha
            except StaleAssessment:
                continue
        # An incomplete poll must not retain an ETag that would suppress retries.
        self.store.set_cursor({"rev": rev, "etag": etag if len(done) == len(prs) else None, "prs": done})
        return results


async def poll(pipeline):
    while True:
        try:
            await asyncio.to_thread(pipeline.once)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Poll failed (%s); retrying next interval", type(exc).__name__)
        await asyncio.sleep(pipeline.settings.poll_seconds)
