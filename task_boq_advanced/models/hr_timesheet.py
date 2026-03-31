from odoo import fields, models, _
from odoo.exceptions import UserError


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    boq_task_id = fields.Many2one('project.task', string='BOQ Task', copy=False, index=True)
    boq_line_id = fields.Many2one('project.task.boq.line', string='BOQ Line', copy=False, index=True)


class ProjectTaskBoqLineTimesheetMixin(models.Model):
    _inherit = 'project.task.boq.line'

    def action_create_timesheet_entry(self):
        self.ensure_one()
        if self.section_type != 'labor':
            raise UserError(_('Timesheet entries are only for labor lines.'))
        if not self.task_id.project_id.account_id:
            raise UserError(_('Project analytic account is required for timesheets.'))
        line = self.env['account.analytic.line'].create({'name': self.description, 'project_id': self.task_id.project_id.id, 'task_id': self.task_id.id, 'account_id': self.task_id.project_id.account_id.id, 'unit_amount': self.quantity_actual or self.quantity_planned, 'employee_id': self.employee_id.id, 'boq_task_id': self.task_id.id, 'boq_line_id': self.id})
        return {'type': 'ir.actions.act_window', 'res_model': 'account.analytic.line', 'res_id': line.id, 'view_mode': 'form'}
