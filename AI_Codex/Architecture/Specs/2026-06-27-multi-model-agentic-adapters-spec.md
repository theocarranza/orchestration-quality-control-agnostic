---
title: "Project Specifications: Multi-Model Agentic Adapters"
date: 2026-06-27
type: spec
status: superseded
---

# Project Specifications: Multi-Model Agentic Adapters

## 1. System Architecture

- **Pattern**: Orchestrator-Worker pattern driven by a functional, side-effect-free state machine.
- **Orchestrator Agent**: A long-running manager that maintains the high-level goal, handles the dependency graph (DAG), and processes state transitions via a reactive stream. It **never** executes tasks directly.
- **Sub-Agents (Workers)**: Ephemeral, model-agnostic instances spawned for isolated single tasks. They receive a pristine context window containing universal instructions, translated dialects, and the task payload. Context is destroyed upon completion to prevent token overflow.

## 2. Universal Skill Package (`AI_Codex/Skills/`)

A standard, model-agnostic package structure containing:

- **Contract (`manifest.json`)**: Machine-readable metadata defining skill name, version, input schemas, and expected outputs.
- **Logic (`instructions.md`)**: Human/LLM-readable, raw, model-agnostic directives.
- **Actions (`/tools`)**: A directory of portable CLI executables/scripts allowing language-agnostic tool execution.

## 3. Adapter Middleware (Translation Pipeline)

A series of pure transformations to adapt skills to any model or harness (e.g., Cursor, Claude Desktop):

- **Dialect Transformation**: Maps universal `instructions.md` to target-specific formats (e.g., Anthropic XML tagging, OpenAI system prompts).
- **Tool Binding**: Translates `manifest.json` schemas into native tool-calling JSON schemas for the target LLM API.
- **Protocol Normalization**: Parses native model tool-call outputs back into universal CLI execution commands.

## 4. State Machine & Dependency Queue

- **Immutable Data Structures**: `Task`, `Event`, and `Queue` are treated as immutable records (e.g., using `copyWith` semantics).
- **Task States**: `Blocked`, `Ready`, `In_Progress`, `Completed`, `Blocked_Requires_Review`.
- **Queue Resolution**: Pure functions (reducers) take the current queue state and a new event (e.g., completed task) and return a completely new queue state with downstream dependencies unblocked.
- **Reactive Stream Management**: The Orchestrator subscribes to a stream of events to receive immutable state updates instead of using imperative polling loops.

## 5. Actor-Critic & Circuit Breaker (Reflection Loop)

- **Evaluator Gate**: A deterministic script or Critic-Agent validates worker outputs against `manifest.json` criteria before accepting them.
- **Retry Injection**: If rejected, the task returns to `Ready`, appending the specific critique and failure context to the next Worker's prompt.
- **Circuit Breaker**: A maximum attempt limit (e.g., 3). Upon breach, the task moves to `Blocked_Requires_Review` to prevent infinite loops.
- **System Evolution**: Failed attempts are synced to a ledger. A Meta-Agent can propose instruction updates (Add/Compose/Update) which require explicit human authorization ("IMPLEMENTATION APPROVED") before being saved.

## 6. Hooks & Events

- **Events**: Immutable records describing state changes (e.g., `WorkerSpawnedEvent`, `ArtifactGeneratedEvent`).
- **Hooks**: Listeners subscribed to the event stream that handle **side effects** outside the Orchestrator's pure logic (e.g., Ledger Sync, Telemetry, UI/CLI updates, human-in-the-loop authorization gates).

## 7. Packaging and Local Persistence

- **Implementation**: The infrastructure is distributed as an MCP (Model Context Protocol) server. While architecturally agnostic, Python is recommended for its mature ecosystem.
- **State Storage**: Project-specific data (queues, ledgers, custom rules) is stored locally in a centralized `projects/` directory within the plugin's installation path to avoid polluting the host workspace with hidden folders.

---

# Agent-Facing Implementation Plan

## Phase 1: Foundation (Data Structures & Universal Contract)

1. Define the immutable data classes (`Task`, `Event`, `QueueState`).
2. Draft the exact JSON schema for `manifest.json` to standardize skill inputs, outputs, and tool definitions.
3. Establish the base `Skill` class to load the manifest, `instructions.md`, and CLI tools.

## Phase 2: Core State Engine (Reactive Queue & Reducers)

1. Initialize the reactive Stream mechanism (e.g., `rxpy` or Python `asyncio` streams).
2. Implement pure functional reducers for core state transitions:
   - `handleTaskCompletion()`
   - `handleTaskFailure()`
   - `resolveDependencies()`
3. Build the core Orchestrator event loop that listens to the stream and dispatches tasks to the `Ready` queue.

## Phase 3: The Adapter Middleware

1. Implement **Dialect Translators**: Write pure functions that transform Markdown into Anthropic XML, OpenAI JSON, and generic CLI dialects.
2. Implement **Tool Binders**: Map `manifest.json` schemas to OpenAI's `functions` array and Anthropic's tool-use schemas.
3. Build the **MCP Interface**: Expose the Orchestrator and skills as tools over the Model Context Protocol.

## Phase 4: Actor-Critic & Circuit Breaker

1. Create the **Evaluator Gate**: Run tests or static checks on Worker outputs.
2. Implement **Retry Injection**: Update the reducer to append critiques to a `Task`'s payload on failure.
3. Add the **Circuit Breaker**: Track retry counts, transitioning tasks to `Blocked_Requires_Review` upon hitting the ceiling.
4. Scaffold the **Meta-Agent Logic** for summarizing failure ledgers and proposing instruction updates.

## Phase 5: Hooks & Side-Effect Management

1. Build the **Event Dispatcher**: Ensure the stream emits events (`WorkerSpawnedEvent`, `CircuitBreakerTrippedEvent`).
2. Implement the **CLI/UI Hook**: Provide status updates and progress tracking.
3. Implement the **Authorization Hook**: Pause execution upon `Blocked_Requires_Review` and await the "IMPLEMENTATION APPROVED" input to trigger the `AuthorizationReceivedEvent`.
4. Implement the **Ledger Hook**: Sync technical outcomes to the project's local state.

## Phase 6: Persistence & Distribution

1. Build the local state persistence manager: Route project-specific artifacts, ledgers, and queues to a `projects/` subfolder in the plugin installation directory based on the active `workspace_root`.
2. Finalize the Python package setup (e.g., `pyproject.toml`) for distribution and MCP consumption.
