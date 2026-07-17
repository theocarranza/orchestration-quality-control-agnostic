## Codex adapter execution

This installed Codex edition uses the host-specific nested topology below. It
does not silently fall back to the portable single-agent pipeline:

```text
root Codex session
└── oqc_codex_orchestrator
    ├── oqc_codex_validator
    └── oqc_codex_remediator
```

Before starting either operation:

1. Confirm the custom agent `oqc_codex_orchestrator` is available and the
   effective Codex configuration permits agent nesting to depth 2.
2. If either prerequisite is missing, return a `blocked` result with
   `stage: codex_adapter`, reason code `adapter_not_installed` or
   `insufficient_agent_depth`, and the recovery command documented in
   `adapters/codex/README.md`. Do not execute the single-agent fallback.
3. Spawn exactly one `oqc_codex_orchestrator`. Give it the absolute path of
   this installed skill directory plus the complete input contract
   (`operation`, `targets`, `profile`, `language`, `checkpoint_path`, and
   `decision`, as applicable).
4. Wait for the orchestrator and return its structured result without
   re-reading targets or applying edits in the root session.

The orchestrator is responsible for loading the portable rules and workflows,
spawning the two named workers, and enforcing every deterministic gate. The
Codex hook separately protects pending target files; custom agent identity is
not itself an authorization token.
