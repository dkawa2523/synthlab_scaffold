# Patch: T0501–T0509 task pack

## How to apply
From your repo root (e.g. synthlab_scaffold):

```bash
unzip next_tasks_T0501-T0509.zip -d .
python patch/apply_queue_patch.py patch/queue_patch_T0501_T0509.json
python autodev/run_loop.py --loop
```

## Notes
- This pack adds new tasks (T0501–T0509) that extend rule-based pattern generation and address operational issues
  (realism gap, config validation, multi-label composite, labeling layers/cause hypotheses, coverage report, profiles).
- It also drops example external labeling spec and profile YAMLs under `conf/wafer_particles/...`.
  These are templates and may contain placeholder ranges/hypotheses.
