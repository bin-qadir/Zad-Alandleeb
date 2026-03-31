from io import BytesIO
import xlsxwriter
from odoo import http, models
from odoo.http import request, content_disposition


class ReportBoqDashboardPdf(models.AbstractModel):
    _name = 'report.task_boq_dashboard_owl.report_boq_dashboard_snapshot'
    _description = 'BOQ Dashboard Snapshot PDF'

    def _get_report_values(self, docids, data=None):
        data = data or {}
        company_id = data.get('company_id') or self.env.company.id
        project_id = data.get('project_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        domain = [('company_id', '=', company_id)]
        if project_id:
            domain.append(('project_id', '=', int(project_id)))
        if date_from:
            domain.append(('date_deadline', '>=', date_from))
        if date_to:
            domain.append(('date_deadline', '<=', date_to))
        records = self.env['boq.dashboard.report'].sudo().search(domain)
        def total(field_name): return sum(records.mapped(field_name)) if records else 0
        top_over_budget = {}; top_alerts = {}
        for rec in records:
            pname = rec.project_id.display_name if rec.project_id else 'No Project'
            top_over_budget[pname] = top_over_budget.get(pname, 0) + rec.budget_variance
            top_alerts[pname] = top_alerts.get(pname, 0) + rec.ai_alert_count
        return {'docs': records, 'company': self.env['res.company'].browse(company_id), 'filters': {'project_id': project_id, 'date_from': date_from, 'date_to': date_to}, 'summary': {'total_projects': len(set(records.mapped('project_id').ids)), 'total_tasks': len(records), 'total_cost_planned': total('total_cost_planned'), 'total_cost_actual': total('total_cost_actual'), 'total_sale_planned': total('total_sale_planned'), 'total_profit_planned': total('total_profit_planned'), 'total_profit_actual': total('total_profit_actual'), 'avg_actual_margin': (sum(records.mapped('actual_margin_percent')) / len(records)) if records else 0, 'over_budget_tasks': len(records.filtered(lambda r: r.is_over_budget)), 'delayed_tasks': len(records.filtered(lambda r: r.is_delayed)), 'low_margin_tasks': len(records.filtered(lambda r: r.is_low_margin)), 'ai_alerts': total('ai_alert_count')}, 'top_over_budget_projects': sorted(top_over_budget.items(), key=lambda x: x[1], reverse=True)[:10], 'top_alert_projects': sorted(top_alerts.items(), key=lambda x: x[1], reverse=True)[:10]}


class BoqDashboardExportController(http.Controller):
    @http.route('/boq_dashboard/export_excel', type='http', auth='user')
    def export_excel(self, company_id=None, project_id=None, date_from=None, date_to=None, **kwargs):
        company_id = int(company_id) if company_id else request.env.company.id
        domain = [('company_id', '=', company_id)]
        if project_id:
            domain.append(('project_id', '=', int(project_id)))
        if date_from:
            domain.append(('date_deadline', '>=', date_from))
        if date_to:
            domain.append(('date_deadline', '<=', date_to))
        records = request.env['boq.dashboard.report'].sudo().search(domain)
        output = BytesIO(); workbook = xlsxwriter.Workbook(output, {'in_memory': True}); ws = workbook.add_worksheet('Dashboard')
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14}); head_fmt = workbook.add_format({'bold': True, 'bg_color': '#D9EAF7', 'border': 1}); num_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1}); txt_fmt = workbook.add_format({'border': 1})
        row = 0; ws.write(row, 0, 'BOQ Dashboard Snapshot', title_fmt); row += 2
        def total(field_name): return sum(records.mapped(field_name)) if records else 0
        summary_rows = [('Total Projects', len(set(records.mapped('project_id').ids))), ('Total Tasks', len(records)), ('Planned Cost', total('total_cost_planned')), ('Actual Cost', total('total_cost_actual')), ('Planned Sale', total('total_sale_planned')), ('Planned Profit', total('total_profit_planned')), ('Actual Profit', total('total_profit_actual')), ('Over Budget Tasks', len(records.filtered(lambda r: r.is_over_budget))), ('Delayed Tasks', len(records.filtered(lambda r: r.is_delayed))), ('Low Margin Tasks', len(records.filtered(lambda r: r.is_low_margin))), ('AI Alerts', total('ai_alert_count'))]
        ws.write(row, 0, 'Summary', head_fmt); row += 1
        for label, value in summary_rows:
            ws.write(row, 0, label, txt_fmt); ws.write(row, 1, value, num_fmt if isinstance(value, (int, float)) else txt_fmt); row += 1
        row += 2
        headers = ['Project','Task','Stage','Deadline','Planned Cost','Actual Cost','Variance','Planned Sale','Planned Profit','Actual Profit','Planned Margin %','Actual Margin %','Stock Moves','Purchases','Timesheets','AI Alerts']
        for col, header in enumerate(headers): ws.write(row, col, header, head_fmt)
        row += 1
        for rec in records:
            values = [rec.project_id.display_name if rec.project_id else '', rec.task_id.display_name if rec.task_id else '', rec.stage_id.name if rec.stage_id else '', str(rec.date_deadline or ''), rec.total_cost_planned, rec.total_cost_actual, rec.budget_variance, rec.total_sale_planned, rec.total_profit_planned, rec.total_profit_actual, rec.planned_margin_percent, rec.actual_margin_percent, rec.stock_move_count, rec.purchase_count, rec.timesheet_count, rec.ai_alert_count]
            for col, value in enumerate(values): ws.write(row, col, value, num_fmt if isinstance(value, (int, float)) else txt_fmt)
            row += 1
        ws.set_column(0, 3, 24); ws.set_column(4, 15, 16); workbook.close(); output.seek(0)
        return request.make_response(output.read(), headers=[('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'), ('Content-Disposition', content_disposition('boq_dashboard_snapshot.xlsx'))])
