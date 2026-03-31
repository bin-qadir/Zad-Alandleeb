/** @odoo-module */
import { Component, onWillStart, useState } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';

class BoqKpiDashboard extends Component {
    setup() {
        this.rpc = useService('rpc');
        this.action = useService('action');
        this.state = useState({loading: true, filters: {company_id: null, project_id: null, date_from: null, date_to: null}, options: {companies: [], projects: []}, data: {total_projects: 0, total_tasks: 0, total_cost_planned: 0, total_cost_actual: 0, total_sale_planned: 0, total_profit_planned: 0, total_profit_actual: 0, avg_planned_margin: 0, avg_actual_margin: 0, over_budget_tasks: 0, delayed_tasks: 0, low_margin_tasks: 0, ai_alerts: 0, top_over_budget_projects: [], top_alert_projects: [], mini_series: {cost: [], profit: [], risk: []}}});
        onWillStart(async () => { await this.loadOptions(); await this.loadData(); });
    }
    async loadOptions() { const options = await this.rpc('/boq_dashboard/filter_options', {}); this.state.options = options; this.state.filters.company_id = options.current_company_id; }
    async loadData() { this.state.loading = true; this.state.data = await this.rpc('/boq_dashboard/kpi_data', this.state.filters); this.state.loading = false; }
    async onFilterChange(ev, key) { this.state.filters[key] = ev.target.value || null; await this.loadData(); }
    async clearFilters() { this.state.filters.project_id = null; this.state.filters.date_from = null; this.state.filters.date_to = null; await this.loadData(); }
    formatAmount(value) { return new Intl.NumberFormat().format(value || 0); }
    formatPercent(value) { return `${(value || 0).toFixed(2)}%`; }
    maxSeriesValue(series, keyA='value', keyB=null) { if (!series || !series.length) return 1; const values=[]; for (const item of series) { values.push(item[keyA] || 0); if (keyB) values.push(item[keyB] || 0);} return Math.max(...values, 1); }
    barWidth(value,max) { const width = max ? (value/max)*100 : 0; return `width:${Math.max(width,2)}%`; }
    async openExecutiveDashboard(filterName=null) { const context = {}; if (filterName==='over_budget') context.search_default_filter_over_budget=1; if (filterName==='delayed') context.search_default_filter_delayed=1; if (filterName==='low_margin') context.search_default_filter_low_margin=1; if (filterName==='alerts') context.search_default_filter_has_alerts=1; await this.action.doAction('task_boq_dashboard.action_boq_executive_dashboard',{additionalContext: context}); }
    async openKpiList() { await this.action.doAction('task_boq_dashboard.action_boq_kpi_dashboard'); }
    async openProjectTasks(projectId, projectName='Project') { await this.action.doAction({type:'ir.actions.act_window', name:`Tasks - ${projectName}`, res_model:'boq.dashboard.report', view_mode:'list,pivot,graph', domain:[['project_id','=',projectId]], target:'current'}); }
    exportExcel() { const params = new URLSearchParams(this.state.filters).toString(); window.open(`/boq_dashboard/export_excel?${params}`,'_blank'); }
    async exportPdf() { await this.action.doAction({type:'ir.actions.report', report_type:'qweb-pdf', report_name:'task_boq_dashboard_owl.report_boq_dashboard_snapshot', data:this.state.filters}); }
}
BoqKpiDashboard.template = 'task_boq_dashboard_owl.BoqKpiDashboard';
registry.category('actions').add('task_boq_dashboard_owl.kpi_dashboard_action', BoqKpiDashboard);
