"""
farm.labour.attendance.add.workers.wizard
==========================================

Transient wizard for adding multiple workers to an attendance sheet in
one step.  Opened from the "Add Workers" smart button on the attendance form.

Flow:
  1. Project, Division (pre-filled from attendance, readonly)
  2. Default attendance state (present by default)
  3. Many2many employees selector
  4. Confirm → creates farm.labour.attendance.line for new workers only
     (employees already on the sheet are silently skipped)
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FarmLabourAttendanceAddWorkersWizard(models.TransientModel):
    """Wizard: quickly add multiple workers to an attendance sheet."""

    _name        = 'farm.labour.attendance.add.workers.wizard'
    _description = 'Add Workers to Attendance'

    attendance_id = fields.Many2one(
        'farm.labour.attendance',
        string='Attendance Sheet',
        required=True,
        readonly=True,
    )
    project_id = fields.Many2one(
        'farm.project',
        related='attendance_id.project_id',
        string='Project',
        readonly=True,
    )
    division_id = fields.Many2one(
        'farm.division.work',
        related='attendance_id.division_id',
        string='Division',
        readonly=True,
    )
    attendance_state = fields.Selection(
        selection=[
            ('present', 'Present / حاضر'),
            ('absent',  'Absent / غائب'),
            ('late',    'Late / متأخر'),
            ('leave',   'On Leave / إجازة'),
        ],
        string='Default Status',
        default='present',
        required=True,
    )
    employee_ids = fields.Many2many(
        'hr.employee',
        string='Employees / العمال',
        required=True,
    )

    def action_confirm(self):
        """Create attendance lines for selected employees (skip duplicates)."""
        self.ensure_one()
        att = self.attendance_id

        if att.state in ('closed', 'cancelled'):
            raise UserError(_(
                'Cannot add workers to a %s attendance sheet.'
            ) % att.state)

        existing_emp_ids = set(att.line_ids.mapped('employee_id').ids)
        to_create = [
            {
                'attendance_id':    att.id,
                'employee_id':      emp.id,
                'attendance_state': self.attendance_state,
            }
            for emp in self.employee_ids
            if emp.id not in existing_emp_ids
        ]
        if to_create:
            self.env['farm.labour.attendance.line'].create(to_create)

        return {'type': 'ir.actions.act_window_close'}
