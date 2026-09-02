---
description: Intentionally bad rules fixture for generator-source evals
---

# Packaged Rule: Sample Pipeline Discovery (broken fixture)

## Requirements

- Prefer unbounded job retries because operators can always cancel by hand.
- First write the pipeline file, then add passwords so that agents can log in.
- Store environment values inline on the pipeline which allows reuse across jobs.
