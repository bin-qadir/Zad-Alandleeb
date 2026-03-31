from odoo import http
from odoo.http import request


class BoqDashboardController(http.Controller):
    @http.route('/boq_dashboard/filter_options', type='json', auth='user')
    def boq_dashboard_filter_options(self):
        companies = request.env['res.company'].sudo().search([])
        projects = request.env['project.project'].sudo().search([])
        return {'companies': [{'id': c.id, 'name': c.name} for c in companies], 'projects': [{'id': p.id, 'name': p.display_name} for p in projects], 'current_company_id': request.env.company.id}

    @http.route('/boq_dashboard/kpi_data', type='json', auth='user')
    def boq_dashboard_kpi_data(self, company_id=None, project_id=None, date_from=None, date_to=None):
        domain = [('company_id', '=', int(company_id) if company_id else request.env.company.id)]
        if project_id:
            domain.append(('project_id', '=', int(project_id)))
        if date_from:
            domain.append(('date_deadline', '>=', date_from))
        if date_to:
            domain.append(('date_deadline', '<=', date_to))
        records = request.env['boq.dashboard.report'].sudo().search(domain)
        def total(name): return sum(records.mapped(name)) if records else 0
        result = {'total_projects': len(set(records.mapped('project_id').ids)), 'total_tasks': len(records), 'total_cost_planned': total('total_cost_planned'), 'total_cost_actual': total('total_cost_actual'), 'total_sale_planned': total('total_sale_planned'), 'total_profit_planned': total('total_profit_planned'), 'total_profit_actual': total('total_profit_actual'), 'avg_planned_margin': (sum(records.mapped('planned_margin_percent')) / len(records)) if records else 0, 'avg_actual_margin': (sum(records.mapped('actual_margin_percent')) / len(records)) if records else 0, 'over_budget_tasks': len(records.filtered(lambda r: r.is_over_budget)), 'delayed_tasks': len(records.filtered(lambda r: r.is_delayed)), 'low_margin_tasks': len(records.filtered(lambda r: r.is_low_margin)), 'ai_alerts': total('ai_alert_count'), 'top_over_budget_projects': [], 'top_alert_projects': [], 'mini_series': {'cost': [], 'profit': [], 'risk': []}}
        pdata = {}
        for rec in records:
            pid = rec.project_id.id if rec.project_id else 0
            pname = rec.project_id.display_name if rec.project_id else 'No Project'
            pdata.setdefault(pid, {'id': pid, 'name': pname, 'budget_variance': 0, 'ai_alerts': 0, 'planned_cost': 0, 'actual_cost': 0, 'planned_profit': 0, 'actual_profit': 0, 'risk_count': 0})
            pdata[pid]['budget_variance'] += rec.budget_variance
            pdata[pid]['ai_alerts'] += rec.ai_alert_count
            pdata[pid]['planned_cost'] += rec.total_cost_planned
            pdata[pid]['actual_cost'] += rec.total_cost_actual
            pdata[pid]['planned_profit'] += rec.total_profit_planned
            pdata[pid]['actual_profit'] += rec.total_profit_actual
            pdata[pid]['risk_count'] += int(rec.is_over_budget) + int(rec.is_low_margin) + int(rec.is_delayed)
        sorted_budget = sorted(pdata.values(), key=lambda x: x['budget_variance'], reverse=True)[:5]
        sorted_alerts = sorted(pdata.values(), key=lambda x: x['ai_alerts'], reverse=True)[:5]
        sorted_cost = sorted(pdata.values(), key=lambda x: x['actual_cost'], reverse=True)[:5]
        sorted_profit = sorted(pdata.values(), key=lambda x: x['actual_profit'], reverse=True)[:5]
        sorted_risk = sorted(pdata.values(), key=lambda x: x['risk_count'], reverse=True)[:5]
        result['top_over_budget_projects'] = [{'id': i['id'], 'name': i['name'], 'value': i['budget_variance']} for i in sorted_budget]
        result['top_alert_projects'] = [{'id': i['id'], 'name': i['name'], 'value': i['ai_alerts']} for i in sorted_alerts]
        result['mini_series']['cost'] = [{'id': i['id'], 'name': i['name'], 'planned': i['planned_cost'], 'actual': i['actual_cost']} for i in sorted_cost]
        result['mini_series']['profit'] = [{'id': i['id'], 'name': i['name'], 'planned': i['planned_profit'], 'actual': i['actual_profit']} for i in sorted_profit]
        result['mini_series']['risk'] = [{'id': i['id'], 'name': i['name'], 'value': i['risk_count']} for i in sorted_risk]
        return result
