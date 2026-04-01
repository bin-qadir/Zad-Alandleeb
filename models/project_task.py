# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ProjectTask(models.Model):
    _inherit = 'project.task'

    boq_line_ids = fields.One2many('task.boq.line', 'task_id', string='BOQ Lines')
    ai_alert_ids = fields.One2many('task.ai.alert', 'task_id', string='AI Alerts')

    boq_line_count = fields.Integer(string='BOQ Lines Count', compute='_compute_boq_metrics')
    budget_total = fields.Monetary(string='Budget Total', compute='_compute_boq_metrics', currency_field='company_currency_id')
    actual_cost_total = fields.Monetary(string='Actual Cost Total', compute='_compute_boq_metrics', currency_field='company_currency_id')
    sale_total = fields.Monetary(string='Sale Total', compute='_compute_boq_metrics', currency_field='company_currency_id')
    profit_total = fields.Monetary(string='Profit Total', compute='_compute_boq_metrics', currency_field='company_currency_id')
    profit_percent = fields.Float(string='Profit %', compute='_compute_boq_metrics', digits=(16, 2))

    ai_alert_count = fields.Integer(string='AI Alert Count', compute='_compute_boq_metrics')
    ai_risk_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], string='AI Risk Level', compute='_compute_boq_metrics', store=True)

    ai_status = fields.Selection([
        ('normal', 'Normal'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ], string='AI Status', compute='_compute_boq_metrics', store=True)

    need_procurement = fields.Boolean(string='Need Procurement', compute='_compute_boq_metrics', store=True)
    over_budget = fields.Boolean(string='Over Budget', compute='_compute_boq_metrics', store=True)
    delayed_flag = fields.Boolean(string='Delayed', compute='_compute_boq_metrics', store=True)

    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)

    @api.depends(
        'boq_line_ids',
        'boq_line_ids.total_cost',
        'boq_line_ids.sale_total',
        'boq_line_ids.profit_amount',
        'boq_line_ids.procurement_state',
        'boq_line_ids.over_budget',
        'boq_line_ids.delayed_flag',
        'ai_alert_ids.severity',
        'ai_alert_ids.state',
    )
    def _compute_boq_metrics(self):
        for rec in self:
            boq_lines = rec.boq_line_ids
            open_alerts = rec.ai_alert_ids.filtered(lambda a: a.state not in ['resolved', 'ignored'])

            rec.boq_line_count = len(boq_lines)
            rec.budget_total = sum(boq_lines.mapped('total_cost'))
            rec.actual_cost_total = sum(boq_lines.mapped('total_cost'))
            rec.sale_total = sum(boq_lines.mapped('sale_total'))
            rec.profit_total = sum(boq_lines.mapped('profit_amount'))
            rec.profit_percent = (rec.profit_total / rec.actual_cost_total * 100.0) if rec.actual_cost_total else 0.0
            rec.ai_alert_count = len(rec.ai_alert_ids)

            rec.need_procurement = any(line.procurement_state in ['to_procure', 'in_progress'] for line in boq_lines)
            rec.over_budget = any(boq_lines.mapped('over_budget'))
            rec.delayed_flag = any(boq_lines.mapped('delayed_flag'))

            severities = open_alerts.mapped('severity')
            if 'critical' in severities:
                rec.ai_risk_level = 'critical'
                rec.ai_status = 'critical'
            elif 'high' in severities:
                rec.ai_risk_level = 'high'
                rec.ai_status = 'warning'
            elif 'medium' in severities:
                rec.ai_risk_level = 'medium'
                rec.ai_status = 'warning'
            else:
                rec.ai_risk_level = 'low'
                rec.ai_status = 'normal'

    def ai_run_rules(self):
        Alert = self.env['task.ai.alert']

        for task in self.search([]):
            if task.planned_hours and task.effective_hours > task.planned_hours:
                existing = Alert.search([
                    ('task_id', '=', task.id),
                    ('alert_type', '=', 'delay'),
                    ('state', 'in', ['new', 'open', 'in_progress']),
                ], limit=1)
                if not existing:
                    Alert.create({
                        'name': _('Task Delay Detected'),
                        'alert_type': 'delay',
                        'severity': 'high',
                        'project_id': task.project_id.id,
                        'task_id': task.id,
                        'description': _('Effective hours exceeded planned hours.'),
                        'reason': _('Task consumed more hours than planned.'),
                        'recommendation': _('Review labor allocation and execution plan.'),
                        'assigned_user_id': self.env.user.id,
                    })

            for boq in task.boq_line_ids:
                if boq.sale_total > 0 and boq.total_cost > boq.sale_total:
                    existing = Alert.search([
                        ('boq_line_id', '=', boq.id),
                        ('alert_type', '=', 'loss_line'),
                        ('state', 'in', ['new', 'open', 'in_progress']),
                    ], limit=1)
                    if not existing:
                        Alert.create({
                            'name': _('Loss BOQ Line Detected'),
                            'alert_type': 'loss_line',
                            'severity': 'critical',
                            'project_id': boq.project_id.id,
                            'task_id': boq.task_id.id,
                            'boq_line_id': boq.id,
                            'description': _('BOQ line total cost is higher than sale total.'),
                            'reason': _('Cost overrun against selling value.'),
                            'recommendation': _('Review cost structure or sale price.'),
                            'assigned_user_id': self.env.user.id,
                        })

            pending_procurement = task.boq_line_ids.filtered(
                lambda l: l.procurement_state in ['to_procure', 'in_progress']
            )
            if pending_procurement:
                existing = Alert.search([
                    ('task_id', '=', task.id),
                    ('alert_type', '=', 'procurement'),
                    ('state', 'in', ['new', 'open', 'in_progress']),
                ], limit=1)
                if not existing:
                    Alert.create({
                        'name': _('Procurement Pending'),
                        'alert_type': 'procurement',
                        'severity': 'medium',
                        'project_id': task.project_id.id,
                        'task_id': task.id,
                        'description': _('There are BOQ lines waiting for procurement action.'),
                        'reason': _('Some required resources are not yet fully procured.'),
                        'recommendation': _('Create RFQs or purchase orders for pending items.'),
                        'assigned_user_id': self.env.user.id,
                    })
        return True

    def action_open_boq_lines(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQ Lines'),
            'res_model': 'task.boq.line',
            'view_mode': 'list,form',
            'domain': [('task_id', 'in', self.ids)],
            'context': {
                'default_task_id': self.id if len(self) == 1 else False,
                'default_project_id': self.project_id.id if len(self) == 1 and self.project_id else False,
            },
        }

    def action_open_ai_alerts(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('AI Alerts'),
            'res_model': 'task.ai.alert',
            'view_mode': 'list,form',
            'domain': [('task_id', 'in', self.ids)],
            'context': {'default_task_id': self.id if len(self) == 1 else False},
        }
