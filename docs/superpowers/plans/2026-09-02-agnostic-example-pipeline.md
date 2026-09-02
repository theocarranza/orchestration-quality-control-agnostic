# Agnostic Example-Pipeline Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline; implementation already approved). Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Ship a product-agnostic core plus one fictional `example-pipeline` profile, and remove every former product/predecessor/mobile-test-stack string from the repository.

**Architecture:** Keep the generic profile mechanism. Add `profiles/example-pipeline/` with classification globs, P1–P6 artifact rules, and four evals. Delete the former product profile, Claude predecessor aliases, and the archived predecessor tree. Rewrite docs/ADRs/CHANGELOG/vault. Breaking 3.0.0.

**Tech Stack:** Python 3.10+ stdlib scripts, Agent Skills package layout, unittest.

## Global Constraints

- Version floor: package and adapter `VERSION` values are `3.0.0`.
- Search gate must be zero matches after this rewrite.
- Unknown profile ids keep existing `unknown_profile` / `blocked`; no compatibility shim.
- No commits unless the user asks.
- Vault file deletes are authorized.
- Implementation is authorized.

## Tasks

- [x] Task 1: Classify tests for the example profile
- [x] Task 2: `example-pipeline` profile package
- [x] Task 3: Claude command set is `/oqc-*` only
- [x] Task 4: Version 3.0.0 and schema examples
- [x] Task 5: Docs, ADRs, eval-harness, SKILL, root README
- [x] Task 6: Delete former product profile and archived predecessor tree
- [x] Task 7: Vault prune and redact
- [x] Task 8: Rewrite design spec and search gate
