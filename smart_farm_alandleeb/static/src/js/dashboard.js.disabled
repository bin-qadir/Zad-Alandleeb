/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

// ─── Tiny chart renderer (vanilla Canvas — no Chart.js dependency) ──────────
function drawBarChart(canvas, labels, datasets, options = {}) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width  = canvas.offsetWidth  || 600;
    const H = canvas.height = canvas.offsetHeight || 280;
    ctx.clearRect(0, 0, W, H);

    const PAD   = { top: 24, right: 20, bottom: 60, left: 72 };
    const cW    = W - PAD.left - PAD.right;
    const cH    = H - PAD.top  - PAD.bottom;
    const n     = labels.length;
    if (!n) { _drawEmpty(ctx, W, H); return; }

    const allVals  = datasets.flatMap(d => d.data);
    const maxVal   = Math.max(...allVals, 1);
    const minVal   = Math.min(...allVals, 0);
    const range    = maxVal - minVal || 1;

    const groupW   = cW / n;
    const barW     = (groupW * 0.7) / datasets.length;
    const barGap   = groupW * 0.05;

    // Grid lines
    ctx.strokeStyle = "rgba(100,116,139,.15)";
    ctx.lineWidth   = 1;
    const steps = 5;
    for (let i = 0; i <= steps; i++) {
        const y = PAD.top + cH - (i / steps) * cH;
        ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + cW, y); ctx.stroke();
        const val = minVal + (range / steps) * i;
        ctx.fillStyle = "#94a3b8";
        ctx.font = "11px 'Geist Mono', monospace";
        ctx.textAlign = "right";
        ctx.fillText(_fmt(val, options.symbol || ""), PAD.left - 6, y + 4);
    }

    // Bars
    datasets.forEach((ds, di) => {
        ds.data.forEach((val, i) => {
            const barH = Math.abs(val - minVal) / range * cH;
            const x = PAD.left + i * groupW + (groupW * 0.15) + di * (barW + barGap);
            const y = PAD.top + cH - ((val - minVal) / range * cH);
            const radius = 4;

            ctx.fillStyle = ds.color || "#16a34a";
            ctx.beginPath();
            ctx.moveTo(x + radius, y);
            ctx.lineTo(x + barW - radius, y);
            ctx.quadraticCurveTo(x + barW, y, x + barW, y + radius);
            ctx.lineTo(x + barW, y + barH);
            ctx.lineTo(x, y + barH);
            ctx.lineTo(x, y + radius);
            ctx.quadraticCurveTo(x, y, x + radius, y);
            ctx.closePath();
            ctx.fill();
        });
    });

    // X labels
    ctx.fillStyle = "#64748b";
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "center";
    labels.forEach((lbl, i) => {
        const x = PAD.left + i * groupW + groupW / 2;
        const y = PAD.top + cH + 18;
        const text = lbl.length > 14 ? lbl.slice(0, 13) + "…" : lbl;
        ctx.fillText(text, x, y);
    });

    // Legend
    if (options.legend) {
        let lx = PAD.left;
        datasets.forEach((ds) => {
            ctx.fillStyle = ds.color;
            ctx.fillRect(lx, H - 18, 10, 10);
            ctx.fillStyle = "#475569";
            ctx.font = "11px system-ui";
            ctx.textAlign = "left";
            ctx.fillText(ds.label, lx + 14, H - 9);
            lx += ctx.measureText(ds.label).width + 32;
        });
    }
}

function drawPieChart(canvas, labels, data, colors) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width  = canvas.offsetWidth  || 300;
    const H = canvas.height = canvas.offsetHeight || 280;
    ctx.clearRect(0, 0, W, H);

    const total = data.reduce((a, b) => a + b, 0);
    if (!total) { _drawEmpty(ctx, W, H); return; }

    const cx = W / 2 - 20;
    const cy = H / 2;
    const r  = Math.min(cx, cy) * 0.78;
    let startAngle = -Math.PI / 2;

    data.forEach((val, i) => {
        const slice = (val / total) * 2 * Math.PI;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, r, startAngle, startAngle + slice);
        ctx.closePath();
        ctx.fillStyle = colors[i] || "#94a3b8";
        ctx.fill();
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2;
        ctx.stroke();

        // Segment label
        const midA = startAngle + slice / 2;
        const lx = cx + Math.cos(midA) * r * 0.62;
        const ly = cy + Math.sin(midA) * r * 0.62;
        const pct = ((val / total) * 100).toFixed(0);
        if (slice > 0.25) {
            ctx.fillStyle = "#fff";
            ctx.font = "bold 12px system-ui";
            ctx.textAlign = "center";
            ctx.fillText(pct + "%", lx, ly + 4);
        }
        startAngle += slice;
    });

    // Legend on right
    const legendX = cx + r + 16;
    labels.forEach((lbl, i) => {
        const ly = cy - (labels.length / 2 - i) * 22 + 8;
        ctx.fillStyle = colors[i] || "#94a3b8";
        ctx.beginPath();
        ctx.arc(legendX + 6, ly - 4, 6, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#475569";
        ctx.font = "12px system-ui";
        ctx.textAlign = "left";
        ctx.fillText(lbl, legendX + 16, ly);
    });
}

function drawLineChart(canvas, labels, datasets, options = {}) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width  = canvas.offsetWidth  || 600;
    const H = canvas.height = canvas.offsetHeight || 240;
    ctx.clearRect(0, 0, W, H);

    const PAD = { top: 20, right: 20, bottom: 55, left: 72 };
    const cW  = W - PAD.left - PAD.right;
    const cH  = H - PAD.top  - PAD.bottom;
    const n   = labels.length;
    if (!n) { _drawEmpty(ctx, W, H); return; }

    const allVals = datasets.flatMap(d => d.data);
    const maxVal  = Math.max(...allVals, 1);
    const minVal  = 0;
    const range   = maxVal - minVal || 1;

    // Grid
    ctx.strokeStyle = "rgba(100,116,139,.15)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = PAD.top + cH - (i / 4) * cH;
        ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + cW, y); ctx.stroke();
        const val = (range / 4) * i;
        ctx.fillStyle = "#94a3b8";
        ctx.font = "11px 'Geist Mono', monospace";
        ctx.textAlign = "right";
        ctx.fillText(_fmt(val, options.symbol || ""), PAD.left - 6, y + 4);
    }

    // Lines
    datasets.forEach(ds => {
        const pts = ds.data.map((val, i) => ({
            x: PAD.left + (i / (n - 1 || 1)) * cW,
            y: PAD.top + cH - ((val - minVal) / range * cH),
        }));

        // Fill
        ctx.beginPath();
        ctx.moveTo(pts[0].x, PAD.top + cH);
        pts.forEach(p => ctx.lineTo(p.x, p.y));
        ctx.lineTo(pts[pts.length - 1].x, PAD.top + cH);
        ctx.closePath();
        ctx.fillStyle = (ds.color || "#16a34a") + "22";
        ctx.fill();

        // Line
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        for (let i = 1; i < pts.length; i++) {
            const cp1x = (pts[i - 1].x + pts[i].x) / 2;
            ctx.bezierCurveTo(cp1x, pts[i - 1].y, cp1x, pts[i].y, pts[i].x, pts[i].y);
        }
        ctx.strokeStyle = ds.color || "#16a34a";
        ctx.lineWidth   = 2.5;
        ctx.stroke();

        // Dots
        pts.forEach(p => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2);
            ctx.fillStyle = ds.color || "#16a34a";
            ctx.fill();
            ctx.strokeStyle = "#fff";
            ctx.lineWidth = 1.5;
            ctx.stroke();
        });
    });

    // X labels
    ctx.fillStyle = "#64748b";
    ctx.font = "11px system-ui";
    ctx.textAlign = "center";
    labels.forEach((lbl, i) => {
        const x = PAD.left + (i / (n - 1 || 1)) * cW;
        ctx.fillText(lbl.replace(/^\d{4}-/, ""), x, PAD.top + cH + 18);
    });

    // Legend
    let lx = PAD.left;
    datasets.forEach(ds => {
        ctx.fillStyle = ds.color || "#16a34a";
        ctx.fillRect(lx, H - 18, 12, 3);
        ctx.fillStyle = "#475569";
        ctx.font = "11px system-ui";
        ctx.textAlign = "left";
        ctx.fillText(ds.label, lx + 16, H - 9);
        lx += ctx.measureText(ds.label).width + 36;
    });
}

function _drawEmpty(ctx, W, H) {
    ctx.fillStyle = "#cbd5e1";
    ctx.font = "14px system-ui";
    ctx.textAlign = "center";
    ctx.fillText("No data available", W / 2, H / 2);
}

function _fmt(val, symbol) {
    if (Math.abs(val) >= 1_000_000) return symbol + (val / 1_000_000).toFixed(1) + "M";
    if (Math.abs(val) >= 1_000)     return symbol + (val / 1_000).toFixed(1)     + "K";
    return symbol + val.toFixed(0);
}

// ─── Owl Dashboard Component ─────────────────────────────────────────────────
export class SmartFarmDashboard extends Component {
    static template = "smart_farm_alandleeb.Dashboard";
    static props = {};

    setup() {
        this.orm      = useService("orm");
        this.action   = useService("action");
        this.notification = useService("notification");

        this.barRef  = useRef("barCanvas");
        this.pieRef  = useRef("pieCanvas");
        this.lineRef = useRef("lineCanvas");

        this.state = useState({
            loading:    true,
            error:      null,
            data:       null,
            filters: {
                project_ids: [],
                stage_ids:   [],
                date_from:   "",
                date_to:     "",
            },
            filterOptions: {
                projects: [],
                stages:   [],
            },
        });

        this._resizeObserver = null;

        onMounted(async () => {
            await this._loadFilterOptions();
            await this._loadData();
            this._setupResizeObserver();
        });

        onWillUnmount(() => {
            if (this._resizeObserver) this._resizeObserver.disconnect();
        });
    }

    async _loadFilterOptions() {
        try {
            const opts = await this.orm.call(
                "smart.farm.dashboard", "get_filter_options", [], {}
            );
            this.state.filterOptions = opts;
        } catch (e) {
            console.error("Dashboard: failed to load filter options", e);
        }
    }

    async _loadData() {
        this.state.loading = true;
        this.state.error   = null;
        try {
            const data = await this.orm.call(
                "smart.farm.dashboard", "get_dashboard_data",
                [], { filters: this.state.filters }
            );
            this.state.data    = data;
            this.state.loading = false;
            // Charts render after DOM update
            setTimeout(() => this._renderCharts(), 50);
        } catch (e) {
            this.state.loading = false;
            this.state.error   = e.message || _t("Failed to load dashboard data");
            console.error("Dashboard error:", e);
        }
    }

    _renderCharts() {
        const d = this.state.data;
        if (!d) return;
        const sym = d.currency_symbol || "";

        if (this.barRef.el) {
            drawBarChart(
                this.barRef.el,
                d.bar_chart.labels,
                [
                    { label: _t("Total Cost"),  data: d.bar_chart.cost,  color: "#ef4444" },
                    { label: _t("Selling Price"), data: d.bar_chart.sales, color: "#16a34a" },
                ],
                { symbol: sym, legend: true }
            );
        }

        if (this.pieRef.el) {
            drawPieChart(
                this.pieRef.el,
                d.pie_chart.labels,
                d.pie_chart.data,
                d.pie_chart.colors
            );
        }

        if (this.lineRef.el) {
            drawLineChart(
                this.lineRef.el,
                d.line_chart.labels,
                [
                    { label: _t("Total Cost"),    data: d.line_chart.total_cost, color: "#ef4444" },
                    { label: _t("Materials"),     data: d.line_chart.material,   color: "#16a34a" },
                    { label: _t("Labor"),         data: d.line_chart.labor,      color: "#2563eb" },
                ],
                { symbol: sym }
            );
        }
    }

    _setupResizeObserver() {
        if (!window.ResizeObserver) return;
        this._resizeObserver = new ResizeObserver(() => this._renderCharts());
        [this.barRef.el, this.pieRef.el, this.lineRef.el].forEach(el => {
            if (el) this._resizeObserver.observe(el);
        });
    }

    // ── Filter handlers ───────────────────────────────────────────────────────

    onProjectChange(ev) {
        const sel = ev.target;
        this.state.filters.project_ids = Array.from(sel.selectedOptions).map(o => parseInt(o.value));
    }

    onStageChange(ev) {
        const sel = ev.target;
        this.state.filters.stage_ids = Array.from(sel.selectedOptions).map(o => parseInt(o.value));
    }

    onDateFromChange(ev) { this.state.filters.date_from = ev.target.value; }
    onDateToChange(ev)   { this.state.filters.date_to   = ev.target.value; }

    onApplyFilters() { this._loadData(); }

    onResetFilters() {
        this.state.filters = { project_ids: [], stage_ids: [], date_from: "", date_to: "" };
        this._loadData();
    }

    // ── Formatting helpers (used in template) ─────────────────────────────────

    fmt(val) {
        if (!this.state.data) return "0";
        const sym = this.state.data.currency_symbol || "";
        const pos = this.state.data.currency_position || "before";
        const abs = Math.abs(val || 0);
        let str;
        if (abs >= 1_000_000) str = (val / 1_000_000).toFixed(2) + "M";
        else if (abs >= 1_000) str = (val / 1_000).toFixed(1) + "K";
        else str = (val || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
        return pos === "before" ? sym + str : str + " " + sym;
    }

    fmtPct(val) { return (val || 0).toFixed(1) + "%"; }

    isProfitable() {
        return this.state.data && (this.state.data.kpi.total_profit >= 0);
    }
}

registry.category("actions").add("smart_farm_dashboard", SmartFarmDashboard);
