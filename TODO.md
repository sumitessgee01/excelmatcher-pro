# TODO (Performance + Export Fixes)

## Phase 1 — Understand + Fix Export reliability
- [ ] Implement async export jobs in `backend/server.py` (export status/result endpoints)
- [ ] Update frontend `src/store/appStore.js` + `src/utils/api.js` to poll export jobs
- [ ] Add save-to-user-selected folder/name using Electron save dialog via IPC

## Phase 2 — Faster load/match
- [ ] Reduce repeated Excel reads by ensuring all match/preview code uses `ctx.df_cache`
- [ ] Avoid returning huge payloads (store internally; return summaries where possible)


