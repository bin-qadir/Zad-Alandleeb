"""
farm.construction.dashboard — Super Agent extension
===================================================
Adds Super AI KPI fields to the construction executive dashboard.
"""
from odoo import api, fields, models, _


class ConstructionDashboardSuperExt(models.Model):
    _inherit = 'farm.construction.dashboard'

    # ── Super AI KPI fields ───────────────────────────────────────────────────

    sai_critical_projects  = fields.Integer(string='Super AI Critical',     compute='_compute_sai_dashboard_kpis', store=False)
    sai_warning_projects   = fields.Integer(string='Super AI Warning',      compute='_compute_sai_dashboard_kpis', store=False)
    sai_procurement_risks  = fields.Integer(string='Super AI Procurement',  compute='_compute_sai_dashboard_kpis', store=False)
    sai_cost_overruns      = fields.Integer(string='Super AI Cost Overruns',compute='_compute_sai_dashboard_kpis', store=False)
    sai_claim_opportunities= fields.Integer(string='Super AI Claim Opps',   compute='_compute_sai_dashboard_kpis', store=False)
    sai_pending_ai_actions = fields.Integer(string='Pending AI Actions',    compute='_compute_sai_dashboard_kpis', store=False)

    def _compute_sai_dashboard_kpis(self):
        for rec in self:
            projects = self.env['farm.project'].search([('business_activity', '=', 'construction')])
            pids     = projects.ids
            scores   = self.env['smart.ai.risk.score'].search([('project_id', 'in', pids)])

            rec.sai_critical_projects   = sum(1 for s in scores if s.status == 'critical')
            rec.sai_warning_projects    = sum(1 for s in scores if s.status == 'warning')
            rec.sai_procurement_risks   = sum(1 for s in scores if s.procurement_risk >= 50)
            rec.sai_cost_overruns       = sum(1 for s in scores if s.cost_risk >= 50)
            rec.sai_claim_opportunities = sum(1 for s in scores if s.claim_risk >= 50)
            rec.sai_pending_ai_actions  = self.env['smart.ai.action'].search_count([
                ('project_id', 'in', pids),
                ('state', 'in', ['draft', 'waiting_approval']),
            ])

    # ── Drill-down actions ────────────────────────────────────────────────────

    def action_sai_critical(self):
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Super AI — Critical Projects'),
            'res_model': 'smart.ai.risk.score',
            'view_mode': 'list,form',
            'domain':    [('status', '=', 'critical')],
        }

    def action_sai_warning(self):
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Super AI — Warning Projects'),
            'res_model': 'smart.ai.risk.score',
            'view_mode': 'list,form',
            'domain':    [('status', '=', 'warning')],
        }

    def action_sai_procurement(self):
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Super AI — Procurement Risks'),
            'res_model': 'smart.ai.risk.score',
            'view_mode': 'list,form',
            'domain':    [('procurement_risk', '>', 49)],
        }

    def action_sai_cost(self):
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Super AI — Cost Overruns'),
            'res_model': 'smart.ai.risk.score',
            'view_mode': 'list,form',
            'domain':    [('cost_risk', '>', 49)],
        }

    def action_sai_claim(self):
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Super AI — Claim Opportunities'),
            'res_model': 'smart.ai.risk.score',
            'view_mode': 'list,form',
            'domain':    [('claim_risk', '>', 49)],
        }

    def action_sai_pending_actions(self):
        projects = self.env['farm.project'].search([('business_activity', '=', 'construction')])
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Super AI — Pending AI Actions'),
            'res_model': 'smart.ai.action',
            'view_mode': 'list,form',
            'domain':    [
                ('project_id', 'in', projects.ids),
                ('state', 'in', ['draft', 'waiting_approval']),
            ],
        }
