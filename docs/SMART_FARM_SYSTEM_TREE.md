# Smart Farm — Complete System Architecture Map

> **Generated:** 2026-04-25 | **Branch:** Dev-ai-work-rev-00 | **Odoo:** 18.0  
> **Scope:** All custom modules under `/home/odoo/src/user`  
> **Mode:** Inspection only — no code changes made.

---

## Table of Contents

1. [Module Tree](#1-module-tree)
2. [Menu Tree](#2-menu-tree)
3. [Model Tree](#3-model-tree)
4. [Workflow Tree](#4-workflow-tree)
5. [BOQ Tree](#5-boq-tree)
6. [Mythos AI Tree](#6-mythos-ai-tree)
7. [Dashboard Tree](#7-dashboard-tree)
8. [Problems & Findings](#8-problems--findings)

---

## 1. Module Tree

### 1.1 Core / Platform Modules

| Module | Name | Purpose | Application | Depends On |
|--------|------|---------|-------------|------------|
| `smart_farm_base` | Smart Farm Base | Root app: defines top-level menu, base tags/stages | ✅ True | `base` |
| `smart_farm_master` | Smart Farm Master | Master data: Crop Types, Cost Types, Work Types, Sensor Types | ❌ | `smart_farm_base` |
| `smart_farm_project` | Smart Farm Project | Core `farm.project` model, fields, `activity.lifecycle.stage` | ❌ | `smart_farm_base`, `smart_farm_master`, `project`, `analytic`, `mail` |
| `smart_farm_work_structure` | Smart Farm Work Structure | Division Works, Subdivision Works, Sub-Subdivision Works hierarchy | ❌ | `smart_farm_base`, `smart_farm_master` |
| `smart_farm_holding` | Smart Farm Holding | Cross-company dashboard, enterprise group menus (deactivated) | ❌ | `smart_farm_base`, `smart_farm_project`, `smart_farm_execution`, `smart_farm_construction`, `smart_farm_agriculture`, `smart_farm_manufacturing`, `smart_farm_livestock` |

### 1.2 BOQ / Costing Modules

| Module | Name | Purpose | Depends On |
|--------|------|---------|------------|
| `smart_farm_boq` | Smart Farm BOQ | `farm.boq` document, `farm.boq.line` hierarchy, templates | `smart_farm_base`, `smart_farm_master`, `smart_farm_project`, `smart_farm_work_structure`, `uom` |
| `smart_farm_costing` | Smart Farm Costing | Per-BOQ-line cost breakdown: Material, Labour, Overhead | `smart_farm_base`, `smart_farm_master`, `smart_farm_boq`, `product` |
| `smart_farm_boq_analysis` | Smart Farm BOQ Analysis | BOQ analysis document with pricing, strategy, approval workflow | `smart_farm_base`, `smart_farm_master`, `smart_farm_boq`, `smart_farm_costing` |
| `smart_farm_boq_lifecycle` | Smart Farm BOQ Lifecycle Tracking | Qty lifecycle across procurement, inspection, claims | `smart_farm_boq_analysis`, `smart_farm_execution`, `smart_farm_procurement`, `smart_farm_material_request` |

### 1.3 Execution / Operations Modules

| Module | Name | Purpose | Depends On |
|--------|------|---------|------------|
| `smart_farm_execution` | Smart Farm Execution | `farm.job.order` core model, material consumption, labour entries, progress logs | `smart_farm_project`, `smart_farm_boq`, `smart_farm_boq_analysis`, `purchase`, `stock`, `hr_timesheet` |
| `smart_farm_procurement` | Smart Farm Procurement | Procurement layer: BOQ Analysis → RFQ → PO → actual cost | `smart_farm_boq_analysis`, `purchase`, `account` |
| `smart_farm_material_request` | Smart Farm Material Request | Material request → RFQ → PO → Receipt cost tracking | `smart_farm_execution`, `smart_farm_procurement`, `smart_farm_dashboard`, `mail` |
| `smart_farm_contract` | Smart Farm Contract | `farm.contract` model: contract between BOQ analysis and JO execution | `smart_farm_boq_analysis`, `smart_farm_execution` |
| `smart_farm_sale_contract` | Smart Farm Sale Contract | Sales Order as approved contract backbone; extends `sale.order` + `farm.contract` | `smart_farm_contract`, `sale_management` |
| `smart_farm_division_pipeline` | Smart Farm Division Pipeline | Division-level workflow pipeline engine | `smart_farm_execution`, `smart_farm_work_structure`, `smart_farm_material_request`, `purchase`, `account` |

### 1.4 Control / Analytics Modules

| Module | Name | Purpose | Depends On |
|--------|------|---------|------------|
| `smart_farm_control` | Smart Farm Control | Phase locking, committed cost, profit/variance engine; extends `farm.project`, `farm.job.order`, `sale.order` | `smart_farm_sale_contract`, `smart_farm_procurement` |
| `smart_farm_pva` | Smart Farm PVA | Planned vs Actual engine — qty, cost, revenue, profit variance | `smart_farm_project`, `smart_farm_execution`, `smart_farm_boq_analysis`, `smart_farm_sale_contract`, `smart_farm_control` |
| `smart_farm_dashboard` | Smart Farm Executive Dashboard | Portfolio KPIs, activity dashboards, construction drill-down (Level 1/2/3) | `smart_farm_control` |

### 1.5 Business Activity Modules

| Module | Name | Purpose | Application | Root Menu Active | Depends On |
|--------|------|---------|-------------|-----------------|------------|
| `smart_farm_construction` | Smart Farm Construction | Construction activity: buildings, zones, floors; extends `farm.project`, `farm.boq`, `farm.job.order` | ❌ | ❌ deactivated | `smart_farm_material_request`, `smart_farm_work_structure` |
| `smart_farm_agriculture` | Smart Farm Agriculture | Agriculture activity: crop plans, seasons, field operations, harvests | ❌ | ❌ deactivated | `smart_farm_material_request`, `smart_farm_work_structure` |
| `smart_farm_livestock` | Smart Farm Livestock | Livestock: herds, animals, health checks, feeding plans | ❌ | ❌ deactivated | `smart_farm_material_request`, `smart_farm_work_structure` |
| `smart_farm_manufacturing` | Smart Farm Manufacturing | Manufacturing: plans, work orders, QC checks | ❌ | ❌ deactivated | `smart_farm_material_request`, `smart_farm_work_structure` |

### 1.6 AI / Mythos Modules

| Module | Name | Purpose | Depends On |
|--------|------|---------|------------|
| `smart_farm_mythos_agents` | Smart Farm Mythos AI Agents | `mythos.agent` registry, agent logs, command center | `smart_farm_construction`, `mail` |
| `smart_farm_super_agent` | Smart Farm Super AI Agent | 10-layer AI brain: context, rules, risk, prediction, RAG, optimization, actions | `smart_farm_construction` |
| `smart_farm_developer_agent` | Smart Farm Developer Agent | AI developer tools: scan code, Studio review, developer tasks | `smart_farm_mythos_agents`, `base`, `web`, `project` |

### 1.7 Legacy / Standalone Modules

| Module | Name | Purpose | Application | Status |
|--------|------|---------|-------------|--------|
| `construction_project` | Construction Project | Legacy construction core: `construction.project`, divisions, subdivisions | ❌ | Root menu: `groups="base.group_no_one"` (hidden) |
| `construction_boq` | Construction BOQ & Costing | Legacy BOQ and cost lines | ❌ | Under `construction_project` legacy root |
| `construction_material` | Construction Material Planning | Legacy material plans and requests | ❌ | Under `construction_project` legacy root |
| `construction_procurement` | Construction Procurement | Legacy procurement | ❌ | Under `construction_project` legacy root |

### 1.8 Utility Modules

| Module | Name | Purpose | Application |
|--------|------|---------|-------------|
| `smart_mail_control_center` | Smart Mail Control Center | Email classification, tracking, follow-up | ✅ True |

---

### Module Load Order (dependency chain)

```
smart_farm_base
  └─ smart_farm_master
       └─ smart_farm_project ── smart_farm_work_structure
            └─ smart_farm_boq
                 └─ smart_farm_costing
                      └─ smart_farm_boq_analysis
                           └─ smart_farm_execution
                                └─ smart_farm_procurement ── smart_farm_material_request
                                     └─ smart_farm_contract
                                          └─ smart_farm_sale_contract
                                               └─ smart_farm_control
                                                    └─ smart_farm_pva
                                                    └─ smart_farm_dashboard ← smart_farm_material_request
                                                    └─ smart_farm_boq_lifecycle
                                                    └─ smart_farm_construction ← smart_farm_work_structure
                                                         └─ smart_farm_agriculture
                                                         └─ smart_farm_livestock
                                                         └─ smart_farm_manufacturing
                                                         └─ smart_farm_mythos_agents
                                                              └─ smart_farm_developer_agent
                                                         └─ smart_farm_super_agent
                                                    └─ smart_farm_holding (all activities)
                                                    └─ smart_farm_division_pipeline
```

---

## 2. Menu Tree

### 2.1 Smart Farm Root (active: ✅)

```
Smart Farm                                          [menu_smart_farm_root]
│
├── Executive Dashboard (hub, no action)            [menu_executive_hub, seq=5]
│   ├── Portfolio Overview                          [menu_farm_dashboard, seq=10]
│   │       action: action_open_farm_dashboard_server → farm.dashboard
│   ├── Analytics                                   [menu_farm_analytics, seq=20]
│   │       action: action_smart_farm_analytics → OWL component
│   ├── Construction                                [menu_farm_dashboard_construction, seq=30]
│   │       action: action_open_construction_projects_dashboard → farm.construction.projects.dashboard
│   ├── Construction Execution   ❌ DEACTIVATED     [menu_farm_dashboard_construction_execution]
│   │       action: action_open_construction_dashboard
│   ├── Civil Division           ❌ DEACTIVATED     [menu_farm_dashboard_civil]
│   │       action: action_open_civil_dashboard
│   ├── Agriculture                                 [menu_farm_dashboard_agriculture, seq=40]
│   │       action: action_open_agriculture_dashboard → farm.activity.dashboard
│   ├── Manufacturing                               [menu_farm_dashboard_manufacturing, seq=50]
│   │       action: action_open_manufacturing_dashboard → farm.activity.dashboard
│   └── Livestock                                   [menu_farm_dashboard_livestock, seq=60]
│           action: action_open_livestock_dashboard → farm.activity.dashboard
│
├── Projects                                        [menu_smart_farm_projects, seq=10]
│   ├── Farm Projects                               [menu_farm_project]
│   │       action: action_farm_project → farm.project (list/form)
│   ├── Fields                                      [menu_farm_field]
│   │       action: action_farm_field → farm.field
│   └── Contracts                                   [menu_farm_contract] (smart_farm_contract)
│           action: action_farm_contract → farm.contract
│
├── Cost Structure                                  [menu_smart_farm_boq] (smart_farm_boq)
│   ├── Project Cost Structures                     [menu_farm_boq]
│   │       action: action_farm_boq → farm.boq
│   ├── Cost Item Templates                         [menu_farm_boq_line_template]
│   │       action: action_farm_boq_line_template → farm.boq.line.template
│   ├── B.O.Q Analysis                              [menu_farm_boq_doc_analysis] (smart_farm_boq_analysis)
│   │       action: action_farm_boq_doc_analysis → farm.boq.analysis
│   ├── BOQ Lifecycle                               [menu_farm_boq_lifecycle] (smart_farm_boq_lifecycle)
│   │       action: action_farm_boq_lifecycle
│   └── Procurement  (container)                    [menu_smart_farm_procurement] (smart_farm_procurement)
│       └── Purchase Orders
│               action: purchase.purchase_rfq → purchase.order
│
├── Execution                                       [menu_smart_farm_execution] (smart_farm_execution)
│   ├── Job Orders                                  [menu_smart_farm_execution_job_orders]
│   │       action: action_farm_job_order → farm.job.order
│   ├── Material Consumption                        [menu_smart_farm_execution_materials]
│   │       action: action_farm_material_consumption → farm.material.consumption
│   ├── Labour Entries                              [menu_smart_farm_execution_labour]
│   │       action: action_farm_labour_entry → farm.labour.entry
│   ├── Progress Tracking                           [menu_smart_farm_execution_progress]
│   │       action: action_farm_job_progress_log → farm.job.progress.log
│   ├── Material Requests                           [menu_smart_farm_material_request] (smart_farm_material_request)
│   │       action: action_farm_material_request → farm.material.request
│   ├── Pending Approvals                           [menu_smart_farm_material_request_pending]
│   │       action: action_farm_material_request_pending
│   └── Division Pipeline                           [menu_farm_division_pipeline] (smart_farm_division_pipeline)
│           action: action_farm_division_pipeline → farm.division.pipeline
│
├── Mythos AI                                       [menu_mythos_ai_root, seq=6] (smart_farm_mythos_agents)
│   ├── Command Center                              [menu_mythos_command_center]
│   │       action: action_mythos_command_center → mythos.agent (kanban)
│   ├── Agents by Domain                            [menu_mythos_construction_agents]
│   │       action: action_mythos_agent → mythos.agent (group_by: agent_layer)
│   ├── Agent Logs                                  [menu_mythos_agent_logs]
│   │       action: action_mythos_agent_log → mythos.agent.log
│   └── Developer Agent  (container)                [menu_developer_agent_root] (smart_farm_developer_agent)
│       ├── Developer Tasks                         [menu_developer_tasks]
│       │       action: action_developer_tasks → mythos.developer.task
│       ├── Scan Code                               [menu_scan_code]
│       │       action: action_scan_code (server action)
│       └── Studio Review                           [menu_studio_review]
│               action: action_studio_review → ir.ui.view (list)
│
├── Holding Dashboard    ❌ DEACTIVATED             [menu_holding_dashboard] (smart_farm_holding)
├── All Companies        ❌ DEACTIVATED             [menu_holding_cross_company]
│   ├── All Projects     ❌ (parent inactive)       [menu_holding_all_farm_projects]
│   ├── Construction Projects ❌                    [menu_holding_all_construction]
│   ├── Agriculture Projects  ❌                    [menu_holding_all_agriculture]
│   ├── Manufacturing Projects ❌                   [menu_holding_all_manufacturing]
│   └── Livestock Projects    ❌                    [menu_holding_all_livestock]
│
└── Configuration                                   [menu_smart_farm_config]
    ├── Settings         (container)                [menu_smart_farm_config_settings]
    │   ├── Tags                                    [menu_smart_farm_tag]
    │   │       action: action_smart_farm_tag → smart.farm.tag
    │   └── Stages                                  [menu_smart_farm_stage]
    │           action: action_smart_farm_stage → smart.farm.stage
    ├── Types            (container)                [menu_smart_farm_config_types] (smart_farm_master)
    │   ├── Crop Types                              [menu_farm_crop_type]
    │   ├── Cost Types                              [menu_farm_cost_type]
    │   ├── Work Types                              [menu_farm_work_type]
    │   └── Sensor Types                            [menu_farm_sensor_type]
    ├── Work Structure   (container)                [menu_smart_farm_config_work_structure] (smart_farm_work_structure)
    │   ├── Division Works                          [menu_farm_division_work]
    │   ├── Subdivision Works                       [menu_farm_subdivision_work]
    │   └── Sub-Subdivision Works                   [menu_farm_sub_subdivision_work]
    ├── Company Activity Setup  ❌ DEACTIVATED      [menu_company_activity_setup] (smart_farm_holding)
    └── Enterprise Groups       ❌ DEACTIVATED      [menu_holding_config_security] (smart_farm_holding)
```

### 2.2 Standalone Activity Roots (all deactivated at DB level)

| Root Menu | XML ID | Module | Status |
|-----------|--------|--------|--------|
| Construction | `menu_sf_construction_root` | `smart_farm_construction` | ❌ `active=False` |
| Agriculture | `menu_sf_agriculture_root` | `smart_farm_agriculture` | ❌ `active=False` |
| Livestock | `menu_sf_livestock_root` | `smart_farm_livestock` | ❌ `active=False` |
| Manufacturing | `menu_sf_manufacturing_root` | `smart_farm_manufacturing` | ❌ `active=False` |
| Construction (Legacy) | `menu_construction_root` | `construction_project` | ✅ active but `groups="base.group_no_one"` |
| Mail Control Center | `menu_mail_control_center_root` | `smart_mail_control_center` | ✅ active — separate app |

### 2.3 Construction Standalone Sub-Menus (deactivated with root)

The following menus are defined but deactivated in `smart_farm_construction/views/menu.xml`:

```
menu_sf_construction_boq, menu_sf_construction_material,
menu_sf_construction_procurement, menu_sf_construction_execution,
menu_sf_construction_inspection, menu_sf_construction_approval,
menu_sf_construction_claims, menu_sf_construction_invoices
```

**Active construction sub-menus** (parent `menu_sf_construction_root`; orphaned when root deactivated — visible only via `smart_farm_super_agent`):

- `menu_sf_construction_ai_command_center` → AI Command Center
- `menu_sf_construction_ai_rules` → AI Rules (under Configuration)
- `menu_sf_construction_ai_knowledge` → Knowledge Docs (under Configuration)

---

## 3. Model Tree

### 3.1 Project Domain

| Model | Description | Key Fields | Relations |
|-------|-------------|-----------|-----------|
| `farm.project` | Core farm project record | `name`, `business_activity` (construction/agriculture/manufacturing/livestock), `state`, `project_phase` (pre_tender→closing), `lifecycle_stage_id`, `start_date`/`end_date`, `project_manager_id`, `analytic_account_id`, `contract_value`, `actual_total_cost`, `is_over_budget`, `project_health`, `project_phase` | M2O: `lifecycle_stage_id`→`activity.lifecycle.stage`, `project_type`→`farm.project.type`, `odoo_project_id`→`project.project`; O2M: `field_ids`→`farm.field` |
| `activity.lifecycle.stage` | Shared lifecycle stage (project + JO) | `name`, `code`, `business_activity`, `sequence` | Used by `farm.project.lifecycle_stage_id` and `farm.job.order.lifecycle_stage_id` |
| `farm.project.type` | Project type classifier | `name` | M2O from `farm.project.project_type` |
| `farm.field` | Farm field/location unit | `name`, `project_id`, location fields | M2O: `farm.project` |
| `smart.farm.tag` | Tag for projects | `name` | M2M from `farm.project.project_tag_ids` |
| `smart.farm.stage` | Stage for projects | `name` | |

**Inherited extensions to `farm.project`:**

| Module | Extension Purpose | Added Fields |
|--------|------------------|-------------|
| `smart_farm_construction` | Construction phase, buildings, zones | `construction_phase`, `building_ids`, `zone_ids` |
| `smart_farm_sale_contract` | Contract value, cost tracking, sale orders | `contract_value`, `estimated_cost`, `actual_total_cost`, `sale_order_ids`, `currency_id`, `company_id` |
| `smart_farm_contract` | Project phase + closing workflow | `project_phase` (pre_tender/tender/contract/execution/closing) |
| `smart_farm_control` | Phase locking, committed cost, variance | `committed_cost`, `cost_variance`, phase lock flags |
| `smart_farm_pva` | Planned vs Actual variance | `jo_planned_revenue`, `jo_actual_revenue`, `jo_revenue_variance`, `jo_profit_variance`, `is_low_margin` |
| `smart_farm_dashboard` | Health score, risk flags | `project_health` (healthy/warning/critical), `is_over_budget`, `is_negative_profit` |
| `smart_farm_super_agent` | AI brain linkage | AI brain smart button |

### 3.2 BOQ Domain

| Model | Description | Key Fields | Relations |
|-------|-------------|-----------|-----------|
| `farm.boq` | BOQ / Cost Structure document | `project_id`, `business_activity`, `state` (draft/submitted/approved/revision), `revision_no`, `is_revision`, `base_boq_id`, `line_ids`, `total`, `progress_percent` | M2O: `farm.project`; O2M: `farm.boq.line` |
| `farm.boq.line` | BOQ line (hierarchy: Division/Subdivision/Sub-Sub/Item) | `display_type`, `row_level` (0=div, 1=sub, 2=sub-sub, 3=item), `division_id`, `subdivision_id`, `sub_subdivision_id`, `quantity`, `unit_price`, `total`, `display_code`, `item_state`, `boq_state` | M2O: `farm.boq`, `farm.division.work`, `farm.subdivision.work`, `farm.sub_subdivision.work`; O2M: children via `child_ids`; Self-referential hierarchy via `parent_id` |
| `farm.boq.line.template` | Reusable BOQ line template | `name`, `division_id`, `subdivision_id`, component sub-lines | O2M: 6 component types |
| `farm.boq.line.template.material` | Template — material component | `product_id`, `quantity`, `unit_price` | |
| `farm.boq.line.template.labor` | Template — labour component | `work_type_id`, `quantity`, `unit_price` | |
| `farm.boq.line.template.subcontractor` | Template — subcontractor | `name`, `quantity`, `unit_price` | |
| `farm.boq.line.template.equipment` | Template — equipment | `name`, `quantity`, `unit_price` | |
| `farm.boq.line.template.tools` | Template — tools | `name`, `quantity`, `unit_price` | |
| `farm.boq.line.template.overhead` | Template — overhead | `name`, `quantity`, `unit_price` | |

### 3.3 Costing Domain

| Model | Description | Key Fields | Relations |
|-------|-------------|-----------|-----------|
| `farm.boq.line.cost` | Cost entry attached to a BOQ line | `boq_line_id`, `cost_type`, `amount` | M2O: `farm.boq.line` |
| `farm.boq.line.material` | Material cost sub-line | `boq_line_id`, `product_id`, `quantity`, `unit_price` | M2O: `farm.boq.line` |
| `farm.boq.line.labor` | Labour cost sub-line | `boq_line_id`, `work_type_id`, `quantity`, `unit_price` | M2O: `farm.boq.line` |
| `farm.boq.line.overhead` | Overhead cost sub-line | `boq_line_id`, `name`, `quantity`, `unit_price` | M2O: `farm.boq.line` |

### 3.4 BOQ Analysis Domain

| Model | Description | Key Fields | Relations |
|-------|-------------|-----------|-----------|
| `farm.boq.analysis` | Analysis document (pricing strategy + approval) | `name`, `project_id`, `boq_id`, `state`, `currency_id` | M2O: `farm.project`, `farm.boq`; O2M: `farm.boq.analysis.line` |
| `farm.boq.analysis.line` | Analysis line (per BOQ item) | `analysis_id`, `boq_line_id`, `name`, `quantity`, `unit_price`, `total`, pricing strategy fields | M2O: `farm.boq.analysis`, `farm.boq.line` |
| `farm.boq.line.analysis` | Detailed analysis of single BOQ line | `boq_line_id`, analysis fields, `state` | M2O: `farm.boq.line` |

**PVA extensions to BOQ Analysis:**

| Module | Extension |
|--------|-----------|
| `smart_farm_pva` | `farm.boq.analysis.line`: `actual_approved_qty`, `actual_claimed_qty`, `qty_variance`, `actual_cost_jos` |

### 3.5 Execution Domain

| Model | Description | Key Fields | Relations |
|-------|-------------|-----------|-----------|
| `farm.job.order` | Job Order — core execution unit | `name`, `project_id`, `boq_id`, `analysis_id`, `boq_line_id`, `analysis_line_id`, `business_activity`, `department` (civil/structure/arch/mechanical/electrical), `jo_stage` (draft→approved→in_progress→…→closed), `lifecycle_stage_id`, `planned_qty`, `unit_price`, `planned_start_date`, `planned_end_date`, `approved_qty`, `claimed_qty`, `claimable_amount`, `claim_amount`, `approved_amount` | M2O: `farm.project`, `farm.boq`, `farm.boq.analysis`, `farm.boq.line`, `farm.boq.analysis.line`, `farm.division.work`, `farm.subdivision.work`; O2M: `farm.job.progress.log` |
| `farm.job.progress.log` | Progress log entry for a JO | `job_order_id`, `date`, `executed_qty`, `note` | M2O: `farm.job.order` |
| `farm.material.consumption` | Material used on a JO | `job_order_id`, `product_id`, `quantity`, `unit_price`, `total_cost` | M2O: `farm.job.order` |
| `farm.labour.entry` | Labour time entry on a JO | `job_order_id`, `employee_id`, `hours`, `unit_cost` | M2O: `farm.job.order` |

**JO Stage Flow:**
```
draft → approved → in_progress → handover_requested → under_inspection
     → accepted (partially_accepted) → ready_for_claim → claimed → closed
```

**Inherited extensions to `farm.job.order`:**

| Module | Extension |
|--------|-----------|
| `smart_farm_construction` | Construction dept fields, AI insights |
| `smart_farm_sale_contract` | `sale_order_id`, `sale_order_line_id`, `task_count` |
| `smart_farm_control` | Phase lock, committed cost enforcement |
| `smart_farm_pva` | `qty_variance`, `sales_variance`, `jo_planned_profit`, `jo_actual_profit`, `jo_profit_variance` |
| `smart_farm_division_pipeline` | Pipeline stage linkage |

### 3.6 Procurement Domain

| Model | Description | Key Fields |
|-------|-------------|-----------|
| `farm.material.request` | Material Request from Job Order | `name`, `project_id`, `job_order_id`, `state` (draft/submitted/approved/rejected/done), `line_ids` |
| `farm.material.request.line` | Material request line | `request_id`, `product_id`, `qty_needed`, `qty_approved` |
| `farm.contract` | Contract document | `name`, `project_id`, `sale_order_id` (from `smart_farm_sale_contract`), `project_phase`, `state` |
| `farm.division.pipeline` | Division workflow pipeline | `name`, `project_id`, `division_id`, `stage` |

**Legacy construction procurement models:**

| Model | Module | Description |
|-------|--------|-------------|
| `construction.material.plan` | `construction_material` | Legacy material plan |
| `construction.material.request` | `construction_material` | Legacy material request |
| `construction.procurement` | `construction_procurement` | Legacy procurement document |

### 3.7 Activity-Specific Models

#### Agriculture

| Model | Description |
|-------|-------------|
| `agriculture.season` | Farming season |
| `agriculture.crop.plan` | Crop plan per season/field |
| `agriculture.field.operation` | Field operation (ploughing, seeding, etc.) |
| `agriculture.harvest` | Harvest record |
| `agriculture.packing` | Packing record |
| `farm.field` | Farm field (shared with base project) |

#### Livestock

| Model | Description |
|-------|-------------|
| `livestock.herd` | Animal herd |
| `livestock.animal` | Individual animal |
| `livestock.health.check` | Veterinary health check |
| `livestock.feeding.plan` | Feeding schedule |
| `livestock.sale` | Livestock sale record |

#### Manufacturing

| Model | Description |
|-------|-------------|
| `manufacturing.plan` | Production plan |
| `manufacturing.work.order` | Work order for a plan |
| `manufacturing.dispatch` | Dispatch record |
| `manufacturing.qc.check` | QC check on a work order |

#### Construction-Specific

| Model | Description |
|-------|-------------|
| `construction.project.building` | Building in a construction project |
| `construction.project.building.floor` | Floor within a building |
| `construction.project.zone` | Zone within a project |
| `construction.ai.insight` | AI insight record for construction |

### 3.8 Mythos AI Domain

| Model | Description | Key Fields |
|-------|-------------|-----------|
| `mythos.agent` | AI Agent registry entry | `name`, `code`, `business_activity`, `agent_layer` (pre_contract/contract/execution/procurement/quality_handover/financial_claims/risk_control/executive_dashboard), `agent_function` (14 functions), `active`, `sequence`, `last_run_datetime`, `last_status`, `run_count`, `insight_count`, `action_count` |
| `mythos.agent.log` | Agent execution log | `agent_id`, `datetime`, `agent_layer`, `title`, `details`, `result`, `related_model`, `related_record_id` |
| `mythos.developer.task` | Developer task from agent scan | `name`, `agent_id`, task fields |
| `smart.super.agent` | Super AI agent command center | 10-layer engine fields |
| `smart.ai.rule` | AI rule — Layer 3 | `name`, `rule_type`, `condition`, `action`, `priority` |
| `smart.ai.context.snapshot` | Context snapshot — Layer 1 | `project_id`, `snapshot_data`, `datetime` |
| `smart.ai.knowledge.document` | Knowledge base — Layer 6 RAG | `name`, `content`, `embedding`, `tags` |
| `smart.ai.optimization.suggestion` | Optimization — Layer 7 | `project_id`, `suggestion_text`, `confidence` |
| `smart.ai.prediction` | Prediction — Layer 5 | `project_id`, `prediction_type`, `value`, `confidence` |
| `smart.ai.risk.score` | Risk score — Layer 4 | `project_id`, `risk_level`, `score`, `factors` |
| `smart.ai.action` | Proposed action — Layers 8-10 | `project_id`, `action_type`, `description`, `approval_state` |

### 3.9 Dashboard Domain

| Model | Description |
|-------|-------------|
| `farm.dashboard` | PMO portfolio singleton dashboard |
| `farm.activity.dashboard` | Activity-specific execution dashboard (one per activity) |
| `farm.construction.projects.dashboard` | Construction portfolio dashboard (Level 1) with smart filter |
| `farm.construction.project.dashboard` | Per-project construction dashboard (Level 2) |
| `farm.civil.dashboard` | Civil division dashboard (Level 3) |
| `farm.structure.dashboard` | Structure division dashboard (Level 3) |
| `farm.arch.dashboard` | Architectural division dashboard (Level 3) |
| `farm.mech.dashboard` | Mechanical division dashboard (Level 3) |
| `farm.elec.dashboard` | Electrical division dashboard (Level 3) |
| `farm.division.dashboard.mixin` | Abstract mixin for L3 division dashboards |

### 3.10 Work Classification (Master Data)

| Model | Description |
|-------|-------------|
| `farm.division.work` | Top-level work classification (Division) |
| `farm.subdivision.work` | Second-level (Subdivision) |
| `farm.sub_subdivision.work` | Third-level (Sub-Subdivision) |
| `farm.crop.type` | Crop type master |
| `farm.cost.type` | Cost type master |
| `farm.work.type` | Work/labour type master |
| `farm.sensor.type` | IoT sensor type master |

### 3.11 Legacy Construction Domain (construction_* modules)

| Model | Description |
|-------|-------------|
| `construction.project` | Legacy construction project |
| `construction.division` | Legacy division |
| `construction.subdivision` | Legacy subdivision |
| `construction.boq` | Legacy BOQ document |
| `construction.boq.line` | Legacy BOQ line |
| `construction.cost.line` | Legacy cost line |
| `construction.material.plan` | Legacy material plan |
| `construction.material.request` | Legacy material request |
| `construction.material.request.line` | Legacy material request line |
| `construction.procurement` | Legacy procurement |
| `construction.procurement.line` | Legacy procurement line |

---

## 4. Workflow Tree

### 4.1 Full Business Flow (Construction Activity)

```
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 1: Project Definition                                         │
│  farm.project  [business_activity=construction]                     │
│  project_phase: pre_tender                                          │
│  Fields: name, project_manager_id, location, analytic_account_id   │
│  Buildings: construction.project.building / zone                   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 2: BOQ Structure                                              │
│  farm.boq  → farm.boq.line (hierarchy)                              │
│  Levels: Division → Subdivision → Sub-Subdivision → Item            │
│  Templates: farm.boq.line.template (6 component types)             │
│  project_phase: tender                                              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 3: Costing Analysis                                           │
│  farm.boq.line.cost + farm.boq.line.material/labor/overhead         │
│  Per-line cost breakdown: material / labour / overhead              │
│  Compute: unit_price, total, gross margin %                         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 4: BOQ Analysis / Quotation                                   │
│  farm.boq.analysis → farm.boq.analysis.line                         │
│  Pricing strategy, client quotation preparation                     │
│  State: draft → submitted → approved                                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 5: Contract / Sales Order                                     │
│  farm.contract ← farm.project (project_phase: contract)            │
│  sale.order [farm_project_id, contract_stage, is_contract_approved] │
│  Approval: draft → sent → approved                                  │
│  project_phase advances to: contract                                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 6: Job Orders — Execution Planning                            │
│  farm.job.order [project_id, analysis_line_id, department]          │
│  jo_stage: draft → approved → in_progress                          │
│  project_phase: execution                                           │
│  Division Pipeline: farm.division.pipeline                          │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 7: Material & Procurement                                     │
│  farm.material.request → farm.material.request.line                 │
│  purchase.order (via RFQ)                                           │
│  Lifecycle: farm.boq.line tracked through procurement               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 8: Execution (on-site)                                        │
│  farm.job.progress.log  (qty executed per date)                     │
│  farm.material.consumption (actual materials used)                  │
│  farm.labour.entry (actual labour hours)                            │
│  jo_stage: in_progress                                              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 9: Inspection & Handover                                      │
│  jo_stage: handover_requested → under_inspection                   │
│  inspection_result: pending/passed/partial/failed                  │
│  accepted_qty set → jo_stage: accepted / partially_accepted         │
│  → ready_for_claim                                                  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 10: Financial Claims                                          │
│  approved_qty × unit_price = approved_amount                        │
│  claimable_amount = (approved_qty − claimed_qty) × unit_price       │
│  jo_stage: claimed                                                  │
│  Mythos AI: financial_claims layer monitors this phase              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 11: Invoicing                                                 │
│  account.move [farm_project_id] (from smart_farm_sale_contract)     │
│  sale.order.line → invoice lines                                    │
│  jo_stage: closed                                                   │
│  project_phase: closing → (Close Project action)                   │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 Financial KPI Chain

```
contract_value            = from farm.contract / sale.order (approved)
estimated_cost            = BOQ total (from farm.boq)
actual_total_cost         = actual_material_cost + actual_labour_cost
committed_cost            = purchase orders not yet received
cost_variance             = contract_value − actual_total_cost
is_over_budget            = actual_total_cost > contract_value
current_profit            = contract_value − actual_total_cost
projected_profit          = contract_value − estimated_cost
gross_margin_pct          = (contract_value − actual_total_cost) / contract_value × 100
project_health            = critical/warning/healthy (computed by smart_farm_dashboard)
```

---

## 5. BOQ Tree

### 5.1 BOQ Document Structure

```
farm.boq  (Project Cost Structure)
│   id, name, project_id, business_activity
│   state: draft → submitted → approved → revision
│   revision_no, base_boq_id (for revisions)
│   project_phase_id (phase this BOQ covers)
│   total (sum of all item lines)
│   progress_percent (approved JOs / total)
│
└── farm.boq.line  (hierarchy — self-referential)
    │
    ├── LEVEL 0  Division Work section header
    │   display_type='line_section', row_level=0
    │   division_id → farm.division.work
    │
    ├── LEVEL 1  Subdivision Work header
    │   display_type='line_section', row_level=1
    │   subdivision_id → farm.subdivision.work
    │
    ├── LEVEL 2  Sub-Subdivision header
    │   display_type='line_section', row_level=2
    │   sub_subdivision_id → farm.sub_subdivision.work
    │
    └── LEVEL 3  BOQ Item (leaf node)
        display_type='item', row_level=3
        display_code, name, description
        boq_qty, quantity, unit_id, unit_price, total
        template_id → farm.boq.line.template
        item_state: draft/submitted/approved/revision
```

### 5.2 BOQ Line Templates

```
farm.boq.line.template
│   name, division_id, subdivision_id
│   unit_id, unit_price
│
├── farm.boq.line.template.material    (product_id, quantity, unit_price)
├── farm.boq.line.template.labor       (work_type_id, quantity, unit_price)
├── farm.boq.line.template.subcontractor (name, scope, unit_price)
├── farm.boq.line.template.equipment   (name, quantity, unit_price)
├── farm.boq.line.template.tools       (name, quantity, unit_price)
└── farm.boq.line.template.overhead    (name, quantity, percentage)
```

### 5.3 Work Structure Hierarchy (master data)

```
farm.division.work          (Level 1 — Division)
    id, name, code, business_activity
    └── farm.subdivision.work  (Level 2 — Subdivision)
            id, name, code, division_id
            └── farm.sub_subdivision.work  (Level 3 — Sub-Subdivision)
                    id, name, code, subdivision_id
```

### 5.4 BOQ Analysis Document

```
farm.boq.analysis  (Pricing & Analysis Document)
│   name, project_id, boq_id
│   state: draft → submitted → approved
│
└── farm.boq.analysis.line  (per BOQ item analysis)
    │   analysis_id, boq_line_id
    │   quantity, unit_price, total
    │   pricing_strategy, margin_pct
    │
    └── farm.boq.line.analysis  (detailed per-item analysis)
            boq_line_id
            competitor_price, recommended_price
            analysis notes
```

---

## 6. Mythos AI Tree

### 6.1 Agent Layer Structure

```
Mythos AI
│
├── Command Center                          (menu_mythos_command_center)
│       model: mythos.agent  (kanban grouped by layer)
│
├── Agents by Domain                        (menu_mythos_construction_agents)
│       model: mythos.agent  (list, group_by: agent_layer)
│       domain: business_activity = construction
│
├── Agent Logs                              (menu_mythos_agent_logs)
│       model: mythos.agent.log
│
└── Developer Agent                         (menu_developer_agent_root)
    ├── Developer Tasks                     → mythos.developer.task
    ├── Scan Code                           → server action (code scan)
    └── Studio Review                       → ir.ui.view (list)
```

### 6.2 Agent Layers (8 operational layers)

| Layer Key | Layer Name | Agent Functions |
|-----------|-----------|-----------------|
| `pre_contract` | Pre-Contract | BOQ Analysis, Costing Analysis, Quotation Review |
| `contract` | Contract | Contract Control |
| `execution` | Execution | Job Order Monitor, Resources Monitor |
| `procurement` | Procurement | Procurement Monitor |
| `quality_handover` | Quality & Handover | Quality Inspection, Handover Control |
| `financial_claims` | Financial Claims | Claims Control, Invoicing Control |
| `risk_control` | Risk & Control | Risk Monitor, Compliance Monitor |
| `executive_dashboard` | Executive Dashboard | Executive Summary |

### 6.3 Agent Functions (14 specific functions)

| Function | Layer | Description |
|----------|-------|-------------|
| `boq_analysis` | Pre-Contract | BOQ item validation, gap analysis |
| `costing_analysis` | Pre-Contract | Cost benchmark, margin check |
| `quotation_review` | Pre-Contract | Pricing strategy review |
| `contract_control` | Contract | Contract terms, approval workflow |
| `job_order_monitor` | Execution | JO progress, overdue detection |
| `resources_monitor` | Execution | Labour/material resource tracking |
| `procurement_monitor` | Procurement | PO delays, supplier compliance |
| `quality_inspection` | Quality & Handover | Inspection pass rates |
| `handover_control` | Quality & Handover | Handover request management |
| `claims_control` | Financial Claims | Claim submission monitoring |
| `invoicing_control` | Financial Claims | Invoice generation tracking |
| `risk_monitor` | Risk & Control | Project risk scoring |
| `compliance_monitor` | Risk & Control | Phase gate compliance |
| `executive_summary` | Executive Dashboard | Portfolio health summary |

### 6.4 Smart Super Agent — 10-Layer Architecture

```
smart.super.agent  (Command Center singleton)
│
├── Layer 1:  smart.ai.context.snapshot     — real-time project context
├── Layer 2:  (rule evaluation)             — built into rule engine
├── Layer 3:  smart.ai.rule                 — if/then rule definitions
├── Layer 4:  smart.ai.risk.score           — risk scoring per project
├── Layer 5:  smart.ai.prediction           — trend/outcome predictions
├── Layer 6:  smart.ai.knowledge.document   — RAG knowledge base
├── Layer 7:  smart.ai.optimization.suggestion — improvement suggestions
├── Layer 8:  smart.ai.action               — proposed actions
├── Layer 9:  (approval gate)               — embedded in smart.ai.action
└── Layer 10: (audit trail)                 — embedded in smart.ai.action
```

---

## 7. Dashboard Tree

### 7.1 Dashboard Hierarchy

```
Smart Farm → Executive Dashboard
│
├── Portfolio Overview  [farm.dashboard]
│   Singleton. Aggregates all farm.project records across activities.
│   KPIs: project counts by phase, health distribution,
│         contract value, actual cost, profit, margin.
│   Drill-down by phase or health to filtered project lists.
│
├── Analytics  [OWL Component: smart_farm_analytics]
│   Chart.js charts: KPI trend (top 10), margin %, cost/revenue by phase,
│   health donut, phase donut.
│   Filter: by project_phase (all/pre_tender/…/closing)
│   Actions: openAll, openOverBudget, openCritical, openWarning
│
├── Construction  [farm.construction.projects.dashboard]  ← Level 1
│   Singleton. Construction portfolio KPI strip (always full portfolio):
│     total_projects, total_contract_value, total_approved_amount,
│     total_claimable_amount, total_claimed_amount, over_budget_count, delayed_count
│   Smart filter strip (no page navigation):
│     ALL → project kanban (all construction projects)
│     DELAYED → project kanban (projects with overdue JOs)
│     OVER BUDGET → project kanban (is_over_budget=True)
│     CLAIMABLE → JO list (claimable_amount > 0)
│     CLAIMED → JO list (claimed_qty > 0)
│   Each project card → Level 2 dashboard
│   Action: action_construction_dashboard_main (canonical)
│
│   └── Per-Project  [farm.construction.project.dashboard]  ← Level 2
│       Per construction project: KPI strip, stage distribution grid (9 stages),
│       department cards (5 departments).
│       Each stage box → filtered JO list for that stage.
│       Each department card → Level 3 dashboard.
│
│       ├── Civil  [farm.civil.dashboard]  ← Level 3
│       │   Subdivision-level breakdown for civil department
│       │
│       ├── Structure  [farm.structure.dashboard]  ← Level 3
│       ├── Architectural  [farm.arch.dashboard]  ← Level 3
│       ├── Mechanical  [farm.mech.dashboard]  ← Level 3
│       └── Electrical  [farm.elec.dashboard]  ← Level 3
│           (All Level 3 use farm.division.dashboard.mixin)
│
├── Agriculture  [farm.activity.dashboard, business_activity=agriculture]
│   Stage distribution, KPIs, progress %.
│   Currently enabled under Executive Dashboard.
│
├── Manufacturing  [farm.activity.dashboard, business_activity=manufacturing]
│   Stage distribution, KPIs.
│   Currently enabled under Executive Dashboard.
│
└── Livestock  [farm.activity.dashboard, business_activity=livestock]
    Stage distribution, KPIs.
    Currently enabled under Executive Dashboard.
```

### 7.2 Dashboard CSS Classes

| Prefix | Module | Dashboard |
|--------|--------|-----------|
| `epd-*` | farm_dashboard.css | Portfolio Overview (Executive Portfolio Dashboard) |
| `cpd-*` | activity_dashboard.css | Construction Projects (Level 1) |
| `cpjd-*` | activity_dashboard.css | Construction Project (Level 2) |
| `cad-*` | activity_dashboard.css | Construction Activity Dashboard |
| `sfa-*` | analytics_dashboard.css | Smart Farm Analytics (OWL) |

---

## 8. Problems & Findings

### 8.1 ✅ Resolved Issues (already fixed in this branch)

| # | Issue | Fix Applied |
|---|-------|-------------|
| 1 | Construction, Agriculture, Livestock, Manufacturing modules appeared as tiles on the Apps dashboard | Set `application: False` in each `__manifest__.py` |
| 2 | Company Activity Setup and Enterprise Groups appeared in Configuration menu | Added `active=False` records in `smart_farm_holding/views/menu.xml` |
| 3 | Activity dashboards (Agriculture, Manufacturing, Livestock) were disabled | Removed the `active=False` deactivation records from `smart_farm_dashboard/views/menu.xml` |
| 4 | Mythos AI was orphaned as a standalone root after Construction root was deactivated | Re-parented `menu_mythos_ai_root` to `smart_farm_base.menu_smart_farm_root` |
| 5 | `project_type` and `master_project_id` fields present in project form | Removed from base form view in `smart_farm_project` |
| 6 | `lifecycle_stage_id` showed JO workflow stages on construction project form | Added `invisible="business_activity == 'construction'"` via xpath in `smart_farm_construction` |
| 7 | `project_phase` selection missing 'Closing' stage | Added 'Closing' with `action_phase_to_closing()` method in `smart_farm_contract` |
| 8 | Smart buttons in project form were in wrong order | Implemented named anchor divs + `position="before"` injection ordering |
| 9 | Construction Dashboard navigated away to separate list views | Replaced with in-page smart filter (filter_type stored field, 5 filter setter methods) |
| 10 | `construction_project` module (Legacy) showed as app tile | Set `application: False` in `construction_project/__manifest__.py` |

---

### 8.2 ⚠️ Outstanding Issues

#### 8.2.1 Missing Access Rights (no `ir.model.access.csv` or empty)

| Module | Models Affected | Risk |
|--------|----------------|------|
| `smart_farm_agriculture` | `agriculture.crop.plan`, `agriculture.season`, `agriculture.field.operation`, `agriculture.harvest`, `agriculture.packing` | Users may get access errors on Agriculture records |
| `smart_farm_livestock` | `livestock.herd`, `livestock.animal`, `livestock.health.check`, `livestock.feeding.plan`, `livestock.sale` | Users may get access errors on Livestock records |
| `smart_farm_manufacturing` | `manufacturing.plan`, `manufacturing.work.order`, `manufacturing.dispatch`, `manufacturing.qc.check` | Users may get access errors on Manufacturing records |
| `smart_farm_procurement` | Models inherited/used in procurement flow | Possible access errors on procurement records |
| `smart_farm_pva` | PVA fields on `farm.project` and `farm.job.order` (inherited, not new model) | Low risk — inherits from covered parent models |
| `smart_farm_sale_contract` | `sale.order` extensions are inherited — no new models | Low risk |
| `smart_farm_boq_lifecycle` | BOQ lifecycle tracking | Check if new models added |
| `smart_farm_control` | Extends `farm.project`, `farm.job.order`, `sale.order` — no new models | Low risk |

#### 8.2.2 Orphaned Menus (parent deactivated, children still defined)

| Menu | XML ID | Module | Situation |
|------|--------|--------|-----------|
| AI Command Center | `menu_sf_construction_ai_command_center` | `smart_farm_super_agent` | Parent `menu_sf_construction_root` is deactivated. This menu is therefore orphaned — not visible to users, not reachable via nav. Consider re-parenting to Mythos AI root or Smart Farm root. |
| AI Rules | `menu_sf_construction_ai_rules` | `smart_farm_super_agent` | Same: parent `menu_sf_construction_config` is deactivated |
| Knowledge Docs | `menu_sf_construction_ai_knowledge` | `smart_farm_super_agent` | Same: parent `menu_sf_construction_config` is deactivated |

#### 8.2.3 Duplicate Root Menus in DB

| Name | Count | Active | Notes |
|------|-------|--------|-------|
| `Manufacturing` | 2 | 1 active (Odoo standard), 1 inactive (Smart Farm standalone) | No conflict — one is standard Odoo `mrp`, other is deactivated Smart Farm root |
| `Construction` | 2 | 0 active (standalone), 1 exists with `group_no_one` (Legacy) | `Construction (Legacy)` is technically active but invisible due to group restriction |

#### 8.2.4 `activity.lifecycle.stage` Dual-Use Problem (partially fixed)

| Issue | Status |
|-------|--------|
| `farm.project.lifecycle_stage_id` and `farm.job.order.lifecycle_stage_id` share the same model | `lifecycle_stage_id` is now hidden for construction projects (fixed). Other activities (agriculture, livestock, manufacturing) still show it on project form — check if their stages are project-relevant or JO-only. |

#### 8.2.5 Holding Dashboard / Cross-Company Menu Deactivated

| Menu | Status | Impact |
|------|--------|--------|
| `menu_holding_dashboard` | ❌ Deactivated | Holding Dashboard view is not accessible via UI |
| `menu_holding_cross_company` | ❌ Deactivated | All "All Companies" cross-company views are hidden |

> **Note:** These were intentionally deactivated. The functionality is available programmatically but not surfaced in the menu. Consider whether a cross-company project view is needed.

#### 8.2.6 Agriculture / Livestock / Manufacturing Activity Models Not Connected to `farm.project`

The standalone activity modules (`smart_farm_agriculture`, `smart_farm_livestock`, `smart_farm_manufacturing`) define their own domain models (seasons, herds, plans) but their connection to `farm.project` passes through `activity.lifecycle.stage` only. There is no `farm.project` in the Agriculture/Livestock/Manufacturing project form — they use their own standalone project forms defined within each module.

The consolidated dashboard (Executive Dashboard → Agriculture/Manufacturing/Livestock) opens `farm.activity.dashboard` filtered by activity, which aggregates `farm.job.order` records — this assumes the JO execution model is used for all activities.

> **Verification needed:** Are `farm.job.order` records actually created for Agriculture/Livestock/Manufacturing activities? Or do these activities use their own independent execution models (`agriculture.field.operation`, `manufacturing.work.order`, etc.)?

#### 8.2.7 `smart_farm_boq_lifecycle` — No Models, Incomplete

The module `smart_farm_boq_lifecycle` has:
- An `ir.model.access.csv` with 0 rules
- A menu item `menu_farm_boq_lifecycle` pointing to `action_farm_boq_lifecycle`
- No Python model files in `models/`

> This module appears **incomplete/placeholder**. The lifecycle tracking action may reference a non-existent model or a model defined via Studio.

#### 8.2.8 Construction Form — Lifecycle Stage for Non-Construction Activities

The `lifecycle_stage_id` field is hidden on the project form **only for construction** (`business_activity == 'construction'`). For other activities, it still shows. If those activities also use JO-workflow stages in `activity.lifecycle.stage`, the same confusion will arise.

#### 8.2.9 `smart_farm_control` — No `ir.model.access.csv`

`smart_farm_control` has models (via `_inherit` on `farm.project`, `farm.job.order`, `sale.order`) but no `security/ir.model.access.csv`. Since it only uses `_inherit`, no new model tables are created — so no new access rules are needed. However, the missing security file means no `res.groups` or record rules are defined in this module.

#### 8.2.10 Legacy Construction Modules Still Installed and Running

The four `construction_*` modules (construction_project, construction_boq, construction_material, construction_procurement) are still installed and running in the database. Their menus are hidden but their models are active:

| Model | Tables in DB | Notes |
|-------|-------------|-------|
| `construction.project` | ✅ | Separate from `farm.project` — old architecture |
| `construction.boq` | ✅ | Separate from `farm.boq` — old architecture |
| `construction.material.plan/request` | ✅ | Replaced by `farm.material.request` |
| `construction.procurement` | ✅ | Replaced by `smart_farm_procurement` |

> These modules are **dead weight** — their data is separate from the Smart Farm engine, menus are hidden, and the Smart Farm engine duplicates all their functionality. Consider deprecating and eventually uninstalling them after confirming no data is needed.

---

### 8.3 Summary of All Menu States

| Menu | Active | Visible To | Notes |
|------|--------|-----------|-------|
| Smart Farm (root) | ✅ | All users | Main entry point |
| Executive Dashboard → Portfolio Overview | ✅ | All users | |
| Executive Dashboard → Analytics | ✅ | All users | OWL component |
| Executive Dashboard → Construction | ✅ | All users | Level 1 dashboard |
| Executive Dashboard → Construction Execution | ❌ | None | Deactivated — use Level 1 instead |
| Executive Dashboard → Civil Division | ❌ | None | Deactivated — reachable from Level 2 |
| Executive Dashboard → Agriculture | ✅ | All users | Activity dashboard |
| Executive Dashboard → Manufacturing | ✅ | All users | Activity dashboard |
| Executive Dashboard → Livestock | ✅ | All users | Activity dashboard |
| Projects → Farm Projects | ✅ | All users | |
| Projects → Fields | ✅ | All users | |
| Projects → Contracts | ✅ | All users | |
| Cost Structure (subtree) | ✅ | All users | BOQ, Analysis, Lifecycle, Procurement |
| Execution (subtree) | ✅ | All users | JOs, Materials, Labour, Progress, MRs, Pipeline |
| Mythos AI (subtree) | ✅ | All users | Command Center, Agents, Logs, Developer |
| Holding Dashboard | ❌ | None | Deactivated |
| All Companies (subtree) | ❌ | None | Deactivated |
| Configuration → Settings | ✅ | All users | Tags, Stages |
| Configuration → Types | ✅ | All users | Crop/Cost/Work/Sensor types |
| Configuration → Work Structure | ✅ | All users | Division/Subdivision works |
| Configuration → Company Activity Setup | ❌ | None | Deactivated |
| Configuration → Enterprise Groups | ❌ | None | Deactivated |
| Construction (standalone root) | ❌ | None | active=False |
| Agriculture (standalone root) | ❌ | None | active=False |
| Livestock (standalone root) | ❌ | None | active=False |
| Manufacturing (standalone root) | ❌ | None | active=False |
| Construction (Legacy) | "✅" | Only `base.group_no_one` | groups restriction — effectively hidden |
| Mail Control Center | ✅ | All users | Separate standalone app |
| AI Command Center | ✅ (menu active) | ⚠️ Parent deactivated | Orphaned — unreachable via nav |
| AI Rules | ✅ (menu active) | ⚠️ Parent deactivated | Orphaned — unreachable via nav |
| Knowledge Docs | ✅ (menu active) | ⚠️ Parent deactivated | Orphaned — unreachable via nav |

---

*Generated by inspection of `/home/odoo/src/user` — no code modified.*
