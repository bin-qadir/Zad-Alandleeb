/** @odoo-module **/
/**
 * SMART FARM — ANALYTICS DASHBOARD (Owl + Chart.js)
 * ==================================================
 *
 * Client-action component registered as "smart_farm_analytics".
 * Fetches live farm.project data via ORM, renders 5 Chart.js charts
 * plus a risk table.  No server-side controller needed.
 *
 * Chart.js is loaded lazily via loadBundle("web.chartjs_lib").
 */

import { Component, onWillStart, onMounted, onWillUnmount, useState, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";

// ── Constants ────────────────────────────────────────────────────────────────

const PHASES = ["pre_tender", "tender", "contract", "execution", "closing"];

const PHASE_LABELS = {
    pre_tender : "Pre-Tender",
    tender     : "Tender",
    contract   : "Contract",
    execution  : "Execution",
    closing    : "Closing",
};

const PHASE_COLORS = {
    pre_tender : "#6366f1",
    tender     : "#f59e0b",
    contract   : "#3b82f6",
    execution  : "#10b981",
    closing    : "#6b7280",
};

const HEALTH_CONFIG = {
    healthy  : { label: "Healthy",  color: "#10b981", border: "#059669" },
    warning  : { label: "Warning",  color: "#f59e0b", border: "#d97706" },
    critical : { label: "Critical", color: "#ef4444", border: "#dc2626" },
};

// ── Number formatters ────────────────────────────────────────────────────────

function fmtShort(val) {
    if (!val && val !== 0) return "0";
    const abs = Math.abs(val);
    if (abs >= 1e9) return (val / 1e9).toFixed(1) + "B";
    if (abs >= 1e6) return (val / 1e6).toFixed(1) + "M";
    if (abs >= 1e3) return (val / 1e3).toFixed(0) + "K";
    return val.toFixed(0);
}

function fmtFull(val) {
    if (!val && val !== 0) return "0";
    return new Intl.NumberFormat("en-US", {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(val);
}

function truncate(str, len = 14) {
    return str && str.length > len ? str.slice(0, len) + "…" : (str || "");
}

// ── Shared Chart.js default options ─────────────────────────────────────────

function gridOpts() {
    return { color: "rgba(0,0,0,0.055)", drawBorder: false };
}

function tooltipCurrencyLabel(ctx) {
    return ` ${ctx.dataset.label}: ${fmtFull(ctx.parsed.y)}`;
}

// ── Component ────────────────────────────────────────────────────────────────

export class SmartFarmAnalyticsDashboard extends Component {
    static template = "smart_farm_dashboard.AnalyticsDashboard";
    static props    = ["action", "actionStack?"];

    setup() {
        this.orm           = useService("orm");
        this.actionService = useService("action");

        this.state = useState({
            loading     : true,
            filterPhase : "all",
            kpis        : {
                totalContractValue : 0,
                totalActualCost    : 0,
                totalProfit        : 0,
                avgMargin          : 0,
            },
            topRisk     : [],
        });

        // Canvas refs (one per chart)
        this.kpiTrendRef    = useRef("kpiTrendCanvas");
        this.marginRef      = useRef("marginCanvas");
        this.costRevenueRef = useRef("costRevenueCanvas");
        this.healthRef      = useRef("healthCanvas");
        this.phaseRef       = useRef("phaseCanvas");

        this._charts = {};

        onWillStart(async () => {
            // Ensure Chart.js (v4) is available as window.Chart
            await loadBundle("web.chartjs_lib");
        });

        onMounted(async () => {
            await this._loadAndRender();
        });

        onWillUnmount(() => {
            this._destroyCharts();
        });
    }

    // ── Filter helpers ───────────────────────────────────────────────────────

    get phaseFilters() {
        return [
            { value: "all",        label: "All Phases" },
            { value: "pre_tender", label: "Pre-Tender" },
            { value: "tender",     label: "Tender" },
            { value: "contract",   label: "Contract" },
            { value: "execution",  label: "Execution" },
            { value: "closing",    label: "Closing" },
        ];
    }

    _getDomain() {
        if (this.state.filterPhase === "all") return [];
        return [["project_phase", "=", this.state.filterPhase]];
    }

    // ── Data loading ─────────────────────────────────────────────────────────

    async _loadAndRender() {
        this.state.loading = true;
        this._destroyCharts();

        const projects = await this.orm.searchRead(
            "farm.project",
            this._getDomain(),
            [
                "name", "project_phase", "project_health",
                "contract_value", "actual_total_cost", "total_committed_cost",
                "estimated_cost", "forecast_final_cost",
                "current_profit", "projected_profit",
                "gross_margin_pct", "is_over_budget", "is_negative_profit",
            ],
            { order: "contract_value desc", limit: 100 }
        );

        const data = this._process(projects);

        // Mutate state — Owl will re-render
        this.state.kpis    = data.kpis;
        this.state.topRisk = data.topRisk;
        this.state.loading = false;

        // One tick for canvases to appear in DOM
        await new Promise((r) => setTimeout(r, 80));

        this._renderKpiTrend(data);
        this._renderMargin(data);
        this._renderCostRevenue(data);
        this._renderHealthDonut(data);
        this._renderPhaseDonut(data);
    }

    // ── Data processing ──────────────────────────────────────────────────────

    _process(projects) {
        // KPI aggregates
        const totalContractValue = projects.reduce((s, p) => s + (p.contract_value       || 0), 0);
        const totalActualCost    = projects.reduce((s, p) => s + (p.actual_total_cost    || 0), 0);
        const totalProfit        = projects.reduce((s, p) => s + (p.current_profit       || 0), 0);

        const execProjs = projects.filter(
            (p) => ["execution", "closing"].includes(p.project_phase) && p.contract_value > 0
        );
        const avgMargin = execProjs.length
            ? execProjs.reduce((s, p) => s + (p.gross_margin_pct || 0), 0) / execProjs.length
            : 0;

        // Phase buckets
        const phaseCounts     = Object.fromEntries(PHASES.map((ph) => [ph, 0]));
        const phaseFinancials = Object.fromEntries(
            PHASES.map((ph) => [ph, { contract: 0, cost: 0, committed: 0 }])
        );
        for (const p of projects) {
            const ph = p.project_phase || "pre_tender";
            if (ph in phaseCounts) {
                phaseCounts[ph]++;
                phaseFinancials[ph].contract  += p.contract_value       || 0;
                phaseFinancials[ph].cost      += p.actual_total_cost    || 0;
                phaseFinancials[ph].committed += p.total_committed_cost || 0;
            }
        }

        // Health counts
        const healthCounts = { healthy: 0, warning: 0, critical: 0 };
        for (const p of projects) {
            const h = p.project_health || "healthy";
            if (h in healthCounts) healthCounts[h]++;
        }

        // Top 10 by contract value for the line / bar charts
        const topByValue = projects.slice(0, 10);

        // Top-risk projects (any warning/critical or over-budget)
        const topRisk = [...projects]
            .filter((p) => p.project_health !== "healthy" || p.is_over_budget)
            .sort((a, b) => {
                const score = { critical: 0, warning: 1, healthy: 2 };
                return (score[a.project_health] || 2) - (score[b.project_health] || 2);
            })
            .slice(0, 10);

        return {
            kpis: { totalContractValue, totalActualCost, totalProfit, avgMargin },
            phaseCounts,
            phaseFinancials,
            healthCounts,
            topByValue,
            topRisk,
        };
    }

    // ── Chart rendering ──────────────────────────────────────────────────────

    _renderKpiTrend(data) {
        const canvas = this.kpiTrendRef.el;
        if (!canvas) return;
        const ps     = data.topByValue;
        const labels = ps.map((p) => truncate(p.name, 13));

        this._charts.kpiTrend = new Chart(canvas, {
            type : "line",
            data : {
                labels,
                datasets : [
                    {
                        label           : "Contract Value",
                        data            : ps.map((p) => p.contract_value    || 0),
                        borderColor     : "#2563eb",
                        backgroundColor : "rgba(37,99,235,0.08)",
                        tension         : 0.38,
                        fill            : true,
                        pointRadius     : 4,
                        borderWidth     : 2,
                    },
                    {
                        label           : "Actual Cost",
                        data            : ps.map((p) => p.actual_total_cost || 0),
                        borderColor     : "#ef4444",
                        backgroundColor : "rgba(239,68,68,0.06)",
                        tension         : 0.38,
                        fill            : true,
                        pointRadius     : 4,
                        borderWidth     : 2,
                    },
                    {
                        label       : "Committed Cost",
                        data        : ps.map((p) => p.total_committed_cost || 0),
                        borderColor : "#f59e0b",
                        borderDash  : [5, 3],
                        tension     : 0.38,
                        fill        : false,
                        pointRadius : 3,
                        borderWidth : 2,
                    },
                    {
                        label           : "Profit",
                        data            : ps.map((p) => p.current_profit || 0),
                        borderColor     : "#10b981",
                        backgroundColor : "rgba(16,185,129,0.07)",
                        tension         : 0.38,
                        fill            : false,
                        pointRadius     : 4,
                        borderWidth     : 2,
                    },
                ],
            },
            options : {
                responsive            : true,
                maintainAspectRatio   : false,
                interaction           : { mode: "index", intersect: false },
                plugins               : {
                    legend  : { position: "top", labels: { font: { size: 12 }, padding: 16 } },
                    tooltip : { callbacks: { label: tooltipCurrencyLabel } },
                },
                scales : {
                    x : { ticks: { font: { size: 11 }, maxRotation: 40 }, grid: gridOpts() },
                    y : { ticks: { callback: fmtShort, font: { size: 11 } }, grid: gridOpts() },
                },
            },
        });
    }

    _renderMargin(data) {
        const canvas = this.marginRef.el;
        if (!canvas) return;
        const ps = data.topByValue.filter((p) => p.contract_value > 0);
        if (!ps.length) return;

        const labels   = ps.map((p) => truncate(p.name, 11));
        const grossPct = ps.map((p) => +(p.gross_margin_pct || 0).toFixed(1));
        const projPct  = ps.map((p) =>
            p.contract_value > 0
                ? +((p.projected_profit / p.contract_value) * 100).toFixed(1)
                : 0
        );
        const barColors = grossPct.map((m) =>
            m < 0   ? "rgba(239,68,68,0.82)" :
            m < 5   ? "rgba(245,158,11,0.82)" :
                      "rgba(16,185,129,0.82)"
        );

        this._charts.margin = new Chart(canvas, {
            type : "bar",
            data : {
                labels,
                datasets : [
                    {
                        label           : "Gross Margin %",
                        data            : grossPct,
                        backgroundColor : barColors,
                        borderColor     : barColors.map((c) => c.replace("0.82", "1")),
                        borderWidth     : 1,
                        borderRadius    : 5,
                    },
                    {
                        label           : "Projected Margin %",
                        type            : "line",
                        data            : projPct,
                        borderColor     : "#6366f1",
                        backgroundColor : "rgba(99,102,241,0.09)",
                        tension         : 0.4,
                        fill            : false,
                        pointRadius     : 4,
                        borderWidth     : 2,
                        borderDash      : [4, 2],
                    },
                ],
            },
            options : {
                responsive          : true,
                maintainAspectRatio : false,
                plugins             : {
                    legend  : { position: "top", labels: { font: { size: 11 } } },
                    tooltip : {
                        callbacks : { label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y}%` },
                    },
                },
                scales : {
                    x : { ticks: { font: { size: 10 }, maxRotation: 45 }, grid: { display: false } },
                    y : { ticks: { callback: (v) => v + "%", font: { size: 11 } }, grid: gridOpts() },
                },
            },
        });
    }

    _renderCostRevenue(data) {
        const canvas = this.costRevenueRef.el;
        if (!canvas) return;
        const labels = PHASES.map((ph) => PHASE_LABELS[ph]);

        this._charts.costRevenue = new Chart(canvas, {
            type : "bar",
            data : {
                labels,
                datasets : [
                    {
                        label           : "Contract Value",
                        data            : PHASES.map((ph) => data.phaseFinancials[ph].contract),
                        backgroundColor : "rgba(37,99,235,0.80)",
                        borderColor     : "#1d4ed8",
                        borderWidth     : 1,
                        borderRadius    : 5,
                    },
                    {
                        label           : "Actual Cost",
                        data            : PHASES.map((ph) => data.phaseFinancials[ph].cost),
                        backgroundColor : "rgba(239,68,68,0.80)",
                        borderColor     : "#dc2626",
                        borderWidth     : 1,
                        borderRadius    : 5,
                    },
                    {
                        label           : "Committed Cost",
                        data            : PHASES.map((ph) => data.phaseFinancials[ph].committed),
                        backgroundColor : "rgba(245,158,11,0.65)",
                        borderColor     : "#d97706",
                        borderWidth     : 1,
                        borderRadius    : 5,
                    },
                ],
            },
            options : {
                responsive          : true,
                maintainAspectRatio : false,
                interaction         : { mode: "index" },
                plugins             : {
                    legend  : { position: "top", labels: { font: { size: 12 }, padding: 14 } },
                    tooltip : { callbacks: { label: tooltipCurrencyLabel } },
                },
                scales : {
                    x : { ticks: { font: { size: 11 } }, grid: { display: false } },
                    y : { ticks: { callback: fmtShort, font: { size: 11 } }, grid: gridOpts() },
                },
            },
        });
    }

    _renderHealthDonut(data) {
        const canvas = this.healthRef.el;
        if (!canvas) return;
        const keys = ["healthy", "warning", "critical"];

        this._charts.healthDonut = new Chart(canvas, {
            type : "doughnut",
            data : {
                labels   : keys.map((k) => HEALTH_CONFIG[k].label),
                datasets : [{
                    data            : keys.map((k) => data.healthCounts[k]),
                    backgroundColor : keys.map((k) => HEALTH_CONFIG[k].color),
                    borderColor     : keys.map((k) => HEALTH_CONFIG[k].border),
                    borderWidth     : 2,
                    hoverOffset     : 8,
                }],
            },
            options : {
                responsive          : true,
                maintainAspectRatio : false,
                cutout              : "68%",
                plugins             : {
                    legend  : { position: "bottom", labels: { padding: 16, font: { size: 12 } } },
                    tooltip : {
                        callbacks : { label: (ctx) => ` ${ctx.label}: ${ctx.parsed} projects` },
                    },
                },
            },
        });
    }

    _renderPhaseDonut(data) {
        const canvas = this.phaseRef.el;
        if (!canvas) return;

        this._charts.phaseDonut = new Chart(canvas, {
            type : "doughnut",
            data : {
                labels   : PHASES.map((ph) => PHASE_LABELS[ph]),
                datasets : [{
                    data            : PHASES.map((ph) => data.phaseCounts[ph]),
                    backgroundColor : PHASES.map((ph) => PHASE_COLORS[ph]),
                    borderColor     : "#ffffff",
                    borderWidth     : 2,
                    hoverOffset     : 8,
                }],
            },
            options : {
                responsive          : true,
                maintainAspectRatio : false,
                cutout              : "68%",
                plugins             : {
                    legend  : { position: "bottom", labels: { padding: 14, font: { size: 12 } } },
                    tooltip : {
                        callbacks : { label: (ctx) => ` ${ctx.label}: ${ctx.parsed} projects` },
                    },
                },
            },
        });
    }

    _destroyCharts() {
        for (const chart of Object.values(this._charts)) {
            try { chart.destroy(); } catch (_) {}
        }
        this._charts = {};
    }

    // ── Template helpers ─────────────────────────────────────────────────────

    fmtCurrency(val) { return fmtFull(val); }

    get profitPositive() { return (this.state.kpis.totalProfit || 0) >= 0; }

    get marginClass() {
        const m = this.state.kpis.avgMargin || 0;
        if (m >= 10) return "sfa-indicator-positive";
        if (m >= 0)  return "sfa-indicator-warning";
        return "sfa-indicator-negative";
    }

    healthLabel(h) { return (HEALTH_CONFIG[h] || HEALTH_CONFIG.healthy).label; }
    healthColor(h) { return (HEALTH_CONFIG[h] || HEALTH_CONFIG.healthy).color; }

    overrunPct(p) {
        if (!p.contract_value) return 0;
        return (((p.actual_total_cost || 0) - p.contract_value) / p.contract_value * 100).toFixed(1);
    }

    // ── Actions ──────────────────────────────────────────────────────────────

    async onFilterPhase(phase) {
        this.state.filterPhase = phase;
        await this._loadAndRender();
    }

    _openList(domain, name) {
        this.actionService.doAction({
            type      : "ir.actions.act_window",
            name,
            res_model : "farm.project",
            view_mode : "list,form",
            domain,
            target    : "current",
        });
    }

    openAll()        { this._openList([], "All Projects"); }
    openOverBudget() { this._openList([["is_over_budget", "=", true]], "Over-Budget Projects"); }
    openCritical()   { this._openList([["project_health", "=", "critical"]], "Critical Projects"); }
    openWarning()    { this._openList([["project_health", "=", "warning"]], "Warning Projects"); }

    openProject(id) {
        this.actionService.doAction({
            type      : "ir.actions.act_window",
            res_model : "farm.project",
            res_id    : id,
            view_mode : "form",
            target    : "current",
        });
    }

    _phaseColor(phase) { return PHASE_COLORS[phase] || "#6b7280"; }
    _phaseLabel(phase) { return PHASE_LABELS[phase] || phase; }
}

registry.category("actions").add("smart_farm_analytics", SmartFarmAnalyticsDashboard);
