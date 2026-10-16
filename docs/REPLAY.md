# Recorded replay

The Pages site uses the same Explorer, benchmark and continuity UI as the local app.
Every saved response comes from the real API on a fresh, isolated FalkorDB ingest.
It is prominently labelled **Replay of recorded FalkorDB results. Run locally for live checks.**
It is not a hosted live assessment service and opens no GitHub PRs.

## Build and inspect

From the repository root, with FalkorDB running:

```powershell
.\.venv\Scripts\python.exe scripts/export_replay.py
.\.venv\Scripts\python.exe -m http.server 8031 --bind 127.0.0.1 --directory site
```

Open `http://127.0.0.1:8031`. In another terminal, `python scripts/check_replay.py`
checks desktop/mobile use of the recorded data. `PREMISE_REPLAY_URL` overrides the URL.
After a UI-only change, `python scripts/export_replay.py --render-only` refreshes the
HTML/assets while retaining the explicitly dated existing recordings.

The generated `site/` directory is ignored. Its index maps canonical HTTP requests to
JSON filenames and SHA-256 hashes. It records model hash, graph revision, evaluation time,
recording time, dates and available people. The exporter deletes only its uniquely owned
temporary graph; it does not delete an existing application graph or output directory.

## Recorded scope

- Overview, entity details, and neighborhoods at depths 1–3.
- Paths between all reasoning nodes in the overview. Other paths report unavailable.
- S1, S1_FIXED, S6 and S12, plus engine-verified combined fixes.
- The committed real benchmark, all questions and labels.
- Departure analyses for Jun, Anika and Ravi.
- Attestation dates/review dates in the slider range, the following days, and the two
  explicit design demonstration dates.

Replay fact sliders are disabled; presets and repairs use recorded responses. The date
slider snaps to recorded dates. Other graph kind selections require a local run. Unsupported
requests show an explicit unavailable message; there is no live-service fallback.

## Publish later

The intended URL is <https://razeefshaik.github.io/Premise/>. **Deployment is not verified**:
this work is committed locally, has not been pushed, and has not been merged into main.
After reviewing/merging/pushing V3, set the repository's Settings → Pages source to
GitHub Actions. The Pages workflow records a fresh graph and deploys on pushes to main
or a manual workflow dispatch. Account Pages permissions still apply.

The workflow follows the [official static Pages starter](https://github.com/actions/starter-workflows/blob/main/pages/static.yml).
No hosted URL, uploaded video, team registration or hackathon submission is claimed.
