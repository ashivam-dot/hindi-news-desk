# Desk state

Written by the scheduled `run` workflow after every pass; never edit by hand while the desk is running.

- `published.json`: every Short that went public (or was scheduled), with its video id, voice engine and
  `orbitwire_overlap` (null, or how it relates to an Orbitwire story).
- `skipped.json`, `retries.json`: stories the desk dropped or will try again, and why.
- `candidates.json`: what the watcher saw on its last pass.
- `health.json`: the last pass's steps, holds and errors (read by the `health` workflow).

Dry runs never write here.
