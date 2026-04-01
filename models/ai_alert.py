# -*- coding: utf-8 -*-
from odoo import fields, models


class TaskAiAlert(models.Model):
    _name = 'task.ai.alert'
    _description = 'Task AI Alert'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Alert Title', required=True, tracking=True)
    active = fields.Boolean(default=True)

    alert_type = fields.Selection([
        ('cost_overrun', 'Cost Overrun'),
        ('loss_line', 'Loss Line'),
        ('delay', 'Delay'),
        ('procurement', 'Procurement Issue'),
        ('inventory', 'Inventory Shortage'),
        ('profit_drop', 'Profit Drop'),
        ('manual', 'Manual'),
    ], string='Alert Type', required=True, tracking=True)

    severity = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], string='Severity', default='medium', required=True, tracking=True)

    state = fields.Selection([
        ('new', 'New'),
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('ignored', 'Ignored'),
    ], string='Status', default='new', tracking=True)

    project_id = fields.Many2one('project.project', string='Project', ondelete='cascade', tracking=True)
    task_id = fields.Many2one('project.task', string='Task', ondelete='cascade', tracking=True)
    boq_line_id = fields.Many2one('task.boq.line', string='BOQ Line', ondelete='cascade', tracking=True)

    company_id = fields.Many2one(
        'res.company',
        related='project_id.company_id',
        store=True,
        readonly=True,
    )

    description = fields.Text(string='Description')
    reason = fields.Text(string='Reason')
    recommendation = fields.Text(string='Recommendation')
    action_taken = fields.Text(string='Action Taken')

    assigned_user_id = fields.Many2one('res.users', string='Assigned To', ondelete='set null', tracking=True)
    resolved_by = fields.Many2one('res.users', string='Resolved By', readonly=True, ondelete='set null')
    resolved_date = fields.Datetime(string='Resolved Date', readonly=True)

    def action_open(self):
        self.write({'state': 'open'})
        return True

    def action_start_progress(self):
        self.write({'state': 'in_progress'})
        return True

    def action_resolve(self):
        self.write({
            'state': 'resolved',
            'resolved_by': self.env.user.id,
            'resolved_date': fields.Datetime.now(),
        })
        return True

    def action_ignore(self):
        self.write({'state': 'ignored'})
        return True
