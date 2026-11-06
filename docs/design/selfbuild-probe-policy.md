# Self-build: low-I/O STRM probe policy

This deployment overrides automatic prefetch described in plugin-strm-prefetch.md.

- `auto_backfill=false` by default, including existing settings missing this field. Startup and files-added do not enumerate pending files. Explicit backfill jobs and opt-in automatic backfill remain supported.
- Playback probes only its selected source through the existing host single-flight/cache mechanism. Favorites never prefetch; series overviews never guess an episode. Detail events select at most one pending file, deduplicated for five minutes and by durable job key. `on_view=false` bypasses this path.
- Plugin jobs serialize probes and query MovieClaw's current activity before every new read; playback/download activity delays work by 60 seconds. An already running probe may finish. **Emby and other readers of the shared mount are not observable here.**
- Per-file failures retain the existing database-backed 1h/6h/1d/3d backoff and source-change invalidation. Two consecutive failed probes pause further plugin probes for 30 minutes (process-local circuit). An actual structured HTTP 403/429 result opens the same circuit immediately. CD2 FUSE errors do not reveal the underlying HTTP status: no inferred HTTP code is used.
- Cached real probe fields remain authoritative. NFO identity/duration/artwork are not invented video/audio specifications; missing codec/track information still requires an on-demand real probe. Existing independent sidecar-artwork ingestion remains unchanged.

Validation: policy unit tests and application/plugin integration tests use synthetic probe results without cloud reads. Production playback acceptance additionally requires bounded response-body reads and decoded frames/seek, never headers alone.
