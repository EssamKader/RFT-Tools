# Reuse Guidelines & Lessons Learned (SimpleBeam to RFT Suite)

This document outlines the mandatory architectural standards, non-negotiable constraints, and reusable patterns inherited from previous tool implementations (e.g., Simple Beam RFT). All contributors and AI agents must adhere to these guidelines to ensure consistency, testability, and clean architecture.

## 1. Core Architectural Principles
* **Strict Core/Adapter Split:** 
  * `core` modules must be pure Python (zero dependencies on `pyrevit`, WPF, or IronPython-only libraries). This enables them to be fully tested under standard `pytest`.
  * Adapters (`script.py` / UI layers) handle the Revit API interaction and contain zero calculation logic.
* **Single Unit Boundary:** Revit uses internal decimal feet; specifications use millimeters. Maintain one designated, strict boundary for mm $\leftrightarrow$ internal-unit conversions.
* **Shared Computation Engine:** The calculation engine must feed both the Review UI/Reports and the actual Revit Placement Transaction. Never duplicate calculations across layers.
* **AST Guards & Mutation Provers:** Because Revit API adapters cannot run in standard unit tests, they are validated via Abstract Syntax Tree (AST) source parsing (`tools/prove_guards.py`). A guard is only valid if it successfully fails when a historical bug/defect is deliberately reintroduced.

## 2. Reusability Audit (Earned, Not Assumed)
Do not blindly import modules across tools. Audit first, state the reasoning in docstrings, and reuse only where structurally sound:
* **`rft.core.spacing`:** Generally reusable for dimension-agnostic vertical spacing math.
* **`rft.core.grades`:** Reusable for bar-type and hook-picker UI conventions.
* **`rft.ui.sketch_palette` & `tools/prove_guards.py`:** Reusable infrastructure for testing and sketching.
* **Explicit Non-Reuse:** 
  * Do not reuse beam face-plan models for columns (columns use a unified perimeter layout).
  * Do not reuse `rft.core.anchorage` for columns (column bar ends are governed strictly by floor-to-floor splice rules).

## 3. AI Developer Directives
* **Zero API Guessing:** Never guess Revit API behaviors. Use MCP tracer bullets and live host verification before writing core code.
* **Mandatory Spec Citations:** Every detailing rule or calculation must cite its specific section in the spec (e.g., `# Spec Ref: Section 4`).
* **Explicit Refusals:** Do not guess missing edge cases. Raise clear exceptions (`NotImplementedError`) and show UI warnings rather than guessing silently.