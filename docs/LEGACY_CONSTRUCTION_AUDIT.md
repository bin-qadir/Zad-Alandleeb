# Legacy Construction Modules — Audit Report

> **Generated:** 2026-04-26 | **Branch:** Dev-ai-work-rev-00 | **Odoo:** 18.0
> **Scope:** construction_project, construction_boq, construction_material, construction_procurement
> **Mode:** Audit + safe UI review only — no business logic changes made.

---

## Executive Summary

Four legacy `construction_*` modules exist in the codebase. They were built as a
standalone construction management system before the Smart Farm engine
(farm.project / farm.job.order / farm.boq) was implemented as the unified platform.

**All legacy modules are already safe:**
- All root menus hidden with `groups="base.group_no_one"` — invisible to all users
- `application: False` on all manifests — hidden from Apps dashboard
- No Smart Farm module depends directly on any `construction_*` module
- All 11 custom models and their data remain intact in the database

**No immediate action required.** This report documents the current state and
provides a deprecation roadmap for a future clean-up sprint.

---

## Module Inventory

### 1. `construction_project` — v18.0.1.0.0

| Property | Value |
|----------|-------|
| **Purpose** | Phase 1 — Core project structure: projects, divisions, subdivisions |
| **Author** | bin-qadir |
| **application** | False (hidden from Apps dashboard) |
| **Depends** | `base`, `mail`, `project`, `analytic` |

#### Models

| Model | Description |
|-------|-------------|
| `construction.project` | Main construction project record. Fields: name, code, client, start/end dates, `project_phase` (Selection: planning/procurement/execution/inspection), `state` (draft/active/on_hold/done/cancelled). Auto-creates Odoo project on save. |
| `construction.division` | Project division (Civil, Structural, Architectural, Mechanical, Electrical). 5 divisions auto-created on project creation. |
| `construction.subdivision` | Sub-division under a division with scope, quantity, unit, rate, total cost. |

#### Security Groups (security.xml)
- `module_category_construction` — category for construction-specific groups
- `group_construction_user` — read/create/write on projects, divisions, subdivisions
- `group_construction_manager` — full CRUD; implied parent of user group

#### Menus (all hidden — `groups="base.group_no_one"`)
```
Construction (Legacy) [menu_construction_root]
  ├── Projects           [menu_construction_projects]
  ├── Divisions          [menu_construction_divisions]
  └── Subdivisions       [menu_construction_subdivisions]
```

#### Actions
- `action_construction_project` → `construction.project` (list, form)
- `action_construction_division` → `construction.division` (list, form)
- `action_construction_subdivision` → `construction.subdivision` (list, form)

---

### 2. `construction_boq` — v18.0.2.0.0

| Property | Value |
|----------|-------|
| **Purpose** | Phase 2 — BOQ document, cost structure, pricing and margin engine |
| **Author** | bin-qadir |
| **application** | False |
| **Depends** | `construction_project`, `product` |

#### Models

| Model | Description |
|-------|-------------|
| `construction.boq` | Bill of Quantities document linked to `construction.project`. States: draft → reviewed → approved / cancelled. Tracks total cost, margin %, contingency. |
| `construction.boq.line` | BOQ line item. Fields: description, quantity, unit, unit_cost, total, profit margin, contingency, total_with_contingency. |
| `construction.cost.line` | Cost breakdown per BOQ line. Type selection: material / labor / subcontract / equipment / tools / overhead / other. |

Also extends `construction.project` (adds boq_ids O2M, boq_count smart button).

#### Menus (all hidden — `groups="base.group_no_one"`)
```
Construction (Legacy)
  ├── Bills of Quantities   [menu_construction_boq]
  └── BOQ Lines             [menu_construction_boq_lines]
```

#### Actions
- `action_construction_boq` → `construction.boq` (list, form)
- `action_construction_boq_line` → `construction.boq.line` (list, form)

---

### 3. `construction_material` — v18.0.3.0.0

| Property | Value |
|----------|-------|
| **Purpose** | Phase 3 — Material planning, material requests, procurement preparation |
| **Author** | bin-qadir |
| **application** | False |
| **Depends** | `construction_boq`, `stock` |

#### Models

| Model | Description |
|-------|-------------|
| `construction.material.plan` | Material plan line linking a BOQ line to a product. Tracks required qty, available qty, shortage. |
| `construction.material.request` | Material request document. Sequence prefix: `MR/YYYY/`. States: draft → submitted → approved → converted_to_procurement. |
| `construction.material.request.line` | Line items in a material request: product, qty, unit, notes. |

Also extends:
- `construction.project` — adds material_request_ids O2M, smart button count
- `construction.boq.line` — adds material_plan_ids O2M, "Generate Material Request" button

#### Sequences
```
construction.material.request  →  MR/YYYY/NNNNN
```

#### Menus (all hidden — `groups="base.group_no_one"`)
```
Construction (Legacy)
  ├── Material Plans      [menu_construction_material_plan]
  └── Material Requests   [menu_construction_material_request]
```

#### Actions
- `action_construction_material_plan` → `construction.material.plan` (list, form)
- `action_construction_material_request` → `construction.material.request` (list, form)

---

### 4. `construction_procurement` — v18.0.4.0.0

| Property | Value |
|----------|-------|
| **Purpose** | Phase 4 — RFQ / Purchase Order / Delivery for construction procurement |
| **Author** | bin-qadir |
| **application** | False |
| **Depends** | `construction_material`, `purchase`, `stock` |

#### Models

| Model | Description |
|-------|-------------|
| `construction.procurement` | Procurement document. Sequence prefix: `CP/YYYY/`. States: draft → rfq → ordered → partially_received → fully_received / cancelled. Links to purchase orders. |
| `construction.procurement.line` | Procurement line items with PO linkage, received qty tracking, delivery status. |

Also extends:
- `construction.material.request` — adds procurement_ids M2M, "Create Procurement" button, Procurements smart button
- `construction.material.request.line` — adds procurement status tracking
- `construction.boq.line` — adds Procurements smart button, readiness metrics

#### Sequences
```
construction.procurement  →  CP/YYYY/NNNNN
```

#### Menus (all hidden — `groups="base.group_no_one"`)
```
Construction (Legacy)
  └── Procurements   [menu_construction_procurement]
```

#### Actions
- `action_construction_procurement` → `construction.procurement` (list, form)

---

## Dependency Graph

```
construction_project  ←── construction_boq
                                ↑
                       construction_material
                                ↑
                       construction_procurement
                                       ↑
                               (depends on: purchase, stock)
```

**Smart Farm modules that reference legacy modules:**

| Smart Farm Module | Dependency on construction_* |
|-------------------|------------------------------|
| `smart_farm_construction` | ❌ None — filtered mirror of farm.project |
| `smart_farm_boq` | ❌ None — independent model (farm.boq) |
| `smart_farm_execution` | ❌ None — uses farm.job.order |
| `smart_farm_dashboard` | ❌ None — queries farm.project/farm.job.order |
| `smart_farm_holding` | ❌ None — depends on smart_farm_construction (not construction_*) |
| **All other smart_farm_*** | ❌ None |

**No Smart Farm module directly depends on any `construction_*` legacy module.**

---

## Duplication Analysis

| Legacy Model | Smart Farm Equivalent | Duplication Assessment |
|---|---|---|
| `construction.project` | `farm.project` (`business_activity='construction'`) | **Full duplicate** — project lifecycle, phase, state, analytic account, Odoo project link |
| `construction.division` | `farm.division.work` (smart_farm_work_structure) | **Functional duplicate** — construction work divisions |
| `construction.subdivision` | `farm.subdivision.work` (smart_farm_work_structure) | **Functional duplicate** — subdivision scopes |
| `construction.boq` | `farm.boq` (smart_farm_boq) | **Full duplicate** — BOQ document with cost structure |
| `construction.boq.line` | `farm.boq.line` (smart_farm_boq) | **Full duplicate** — BOQ line items with pricing |
| `construction.cost.line` | Inline cost fields on `farm.boq.line` | **Functional overlap** — cost type breakdown |
| `construction.material.plan` | `farm.material.request.line` (smart_farm_material_request) | **Functional overlap** — material planning |
| `construction.material.request` | `farm.material.request` (smart_farm_material_request) | **Full duplicate** — material request workflow |
| `construction.material.request.line` | `farm.material.request.line` | **Full duplicate** — request line items |
| `construction.procurement` | `purchase.order` + smart_farm_procurement links | **Functional overlap** — RFQ/PO lifecycle |
| `construction.procurement.line` | `purchase.order.line` | **Functional overlap** — PO lines |

**Conclusion:** The entire legacy stack is functionally superseded by Smart Farm engine modules.

---

## Current UI / Visibility Status

| Module | Menus Active | App Tile Visible | DB Tables | Data Present |
|--------|-------------|-----------------|-----------|--------------|
| `construction_project` | ❌ All hidden (`group_no_one`) | ❌ `application: False` | ✔ Tables exist | Possibly — not migrated |
| `construction_boq` | ❌ All hidden (`group_no_one`) | ❌ `application: False` | ✔ Tables exist | Possibly |
| `construction_material` | ❌ All hidden (`group_no_one`) | ❌ `application: False` | ✔ Tables exist | Possibly |
| `construction_procurement` | ❌ All hidden (`group_no_one`) | ❌ `application: False` | ✔ Tables exist | Possibly |

**All menus are already hidden. No further UI cleanup required.**

---

## Recommendations

### Status: DEPRECATE LATER (safe to keep as-is)

All four modules are already inert from a user-facing perspective. The recommended approach is:

| Module | Recommendation | Rationale |
|--------|---------------|-----------|
| `construction_project` | **Deprecate later** | Defines security groups used by construction_boq chain. Must be last to remove. Tables may hold historical data. |
| `construction_boq` | **Deprecate later** | Depends on construction_project. Full duplicate of farm.boq but no active users. |
| `construction_material` | **Deprecate later** | Depends on construction_boq. Full duplicate of farm.material.request. |
| `construction_procurement` | **Deprecate later** | Depends on construction_material. Partially overlaps purchase.order flow. |

### Safe to do now
- ✔ Nothing — all menus already hidden, all app tiles already hidden
- ✔ Modules can remain installed; they have zero user-facing footprint

### When ready to remove (future sprint)
1. Verify no production data exists in legacy tables
2. Export any historical records needed
3. Uninstall in reverse dependency order:
   `construction_procurement` → `construction_material` → `construction_boq` → `construction_project`
4. After uninstall, delete module directories from the repository

### Do NOT do
- ❌ Do not delete module directories while modules are still installed in the DB
- ❌ Do not drop tables manually — use Odoo uninstall
- ❌ Do not remove security groups without verifying no users are assigned to them

---

## File Structure Summary

```
construction_project/               # 11 files — INSTALLED, all menus hidden
├── __manifest__.py                 # v18.0.1.0.0, application: False
├── models/                         # 3 models: project, division, subdivision
├── security/security.xml           # security groups + record rules
├── security/ir.model.access.csv    # 3 models × 2 roles = 6 rules
└── views/                          # 4 views + menu.xml (all hidden)

construction_boq/                   # 9 files — INSTALLED, all menus hidden
├── __manifest__.py                 # v18.0.2.0.0, depends: construction_project, product
├── models/                         # 3 models + 1 project extend
├── security/ir.model.access.csv    # 3 models × 2 roles = 6 rules
└── views/                          # 3 views + 1 extend + menu.xml (all hidden)

construction_material/              # 12 files — INSTALLED, all menus hidden
├── __manifest__.py                 # v18.0.3.0.0, depends: construction_boq, stock
├── models/                         # 3 models + 2 extends
├── security/ir.model.access.csv    # 3 models × 2 roles = 6 rules
├── data/sequences.xml              # MR/YYYY/ sequence
└── views/                          # 2 views + 2 extends + menu.xml (all hidden)

construction_procurement/           # 12 files — INSTALLED, all menus hidden
├── __manifest__.py                 # v18.0.4.0.0, depends: construction_material, purchase, stock
├── models/                         # 2 models + 3 extends
├── security/ir.model.access.csv    # 2 models × 2 roles = 4 rules
├── data/sequences.xml              # CP/YYYY/ sequence
└── views/                          # 1 view + 2 extends + menu.xml (all hidden)
```

---

## Totals

| Category | Count |
|----------|-------|
| Legacy modules | 4 |
| Custom models defined | 11 |
| Extension models (inherits) | 6 |
| Menu items (all hidden) | 10 |
| Window actions | 8 |
| IR sequences | 2 (MR/, CP/) |
| Access rules | 22 (11 models × 2 roles) |
| Smart Farm modules that depend on them | **0** |

---

*Audit completed 2026-04-26. No code changes were made to legacy modules.*
*Safe UI cleanup: none required — all menus already hidden.*
