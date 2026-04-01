# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ProjectProject(models.Model):
    _inherit = 'project.project'

    boq_line_ids = fields.One2many('task.boq.line', 'project_id', string='BOQ Lines')
    ai_alert_ids = fields.One2many('task.ai.alert', 'project_id', string='AI Alerts')

    total_material_cost = fields.Monetary(string='Total Material Cost', compute='_compute_project_costs', currency_field='currency_id')
    total_labor_cost = fields.Monetary(string='Total Labor Cost', compute='_compute_project_costs', currency_field='currency_id')
    total_overhead_cost = fields.Monetary(string='Total Overhead Cost', compute='_compute_project_costs', currency_field='currency_id')
    total_sale_value = fields.Monetary(string='Total Sale Value', compute='_compute_project_costs', currency_field='currency_id')
    gross_profit = fields.Monetary(string='Gross Profit', compute='_compute_project_costs', currency_field='currency_id')
    gross_margin = fields.Float(string='Gross Margin %', compute='_compute_project_costs', digits=(16, 2))

    boq_line_count = fields.Integer(string='BOQ Line Count', compute='_compute_project_costs')
    ai_alert_count = fields.Integer(string='AI Alert Count', compute='_compute_project_costs')

    need_procurement = fields.Boolean(string='Need Procurement', compute='_compute_project_costs', store=True)
    over_budget = fields.Boolean(string='Over Budget', compute='_compute_project_costs', store=True)
    delayed_flag = fields.Boolean(string='Delayed', compute='_compute_project_costs', store=True)

    @api.depends(
        'boq_line_ids',
        'boq_line_ids.material_cost',
        'boq_line_ids.labor_cost',
        'boq_line_ids.overhead_cost',
        'boq_line_ids.sale_total',
        'boq_line_ids.total_cost',
        'boq_line_ids.procurement_state',
        'boq_line_ids.over_budget',
        'boq_line_ids.delayed_flag',
        'ai_alert_ids.state',
    )
    def _compute_project_costs(self):
        for rec in self:
            boq_lines = rec.boq_line_ids
            total_cost = sum(boq_lines.mapped('total_cost'))

            rec.total_material_cost = sum(boq_lines.mapped('material_cost'))
            rec.total_labor_cost = sum(boq_lines.mapped('labor_cost'))
            rec.total_overhead_cost = sum(boq_lines.mapped('overhead_cost'))
            rec.total_sale_value = sum(boq_lines.mapped('sale_total'))
            rec.gross_profit = rec.total_sale_value - total_cost
            rec.gross_margin = (rec.gross_profit / rec.total_sale_value * 100.0) if rec.total_sale_value else 0.0
            rec.boq_line_count = len(boq_lines)
            rec.ai_alert_count = len(rec.ai_alert_ids)

            rec.need_procurement = any(line.procurement_state in ['to_procure', 'in_progress'] for line in boq_lines)
            rec.over_budget = any(boq_lines.mapped('over_budget'))
            rec.delayed_flag = any(boq_lines.mapped('delayed_flag'))

    def action_open_boq_lines(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQ Lines'),
            'res_model': 'task.boq.line',
            'view_mode': 'list,form',
            'domain': [('project_id', 'in', self.ids)],
            'context': {'default_project_id': self.id if len(self) == 1 else False},
        }

    def action_open_ai_alerts(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('AI Alerts'),
            'res_model': 'task.ai.alert',
            'view_mode': 'list,form',
            'domain': [('project_id', 'in', self.ids)],
            'context': {'default_project_id': self.id if len(self) == 1 else False},
        }
