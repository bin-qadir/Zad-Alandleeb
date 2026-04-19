from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FarmLabourEntry(models.Model):
    """Labour time entry for a Job Order.

    Tracks employee hours and associated cost per job order.
    Optionally links to an hr.timesheet (account.analytic.line) when the
    timesheet module is in use, so costs flow through the analytic system.
    """

    _name = 'farm.labour.entry'
    _description = 'Farm Labour Entry'
    _order = 'job_order_id, date desc, id'

    # ── Links ─────────────────────────────────────────────────────────────────
    job_order_id = fields.Many2one(
        'farm.job.order',
        string='Job Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    project_id = fields.Many2one(
        'farm.project',
        string='Project',
        related='job_order_id.project_id',
        store=True,
        readonly=True,
    )

    # ── Employee ──────────────────────────────────────────────────────────────
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='restrict',
    )

    # ── Time ─────────────────────────────────────────────────────────────────
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
    )
    hours = fields.Float(
        string='Hours',
        digits=(16, 2),
        default=1.0,
    )

    # ── Cost ─────────────────────────────────────────────────────────────────
    cost_per_hour = fields.Float(
        string='Cost per Hour',
        digits=(16, 4),
        default=0.0,
    )
    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_total_cost',
        store=True,
        digits=(16, 2),
    )

    # ── Description ──────────────────────────────────────────────────────────
    description = fields.Char(string='Work Description')

    # ── Timesheet link (optional — hr_timesheet) ──────────────────────────────
    timesheet_id = fields.Many2one(
        'account.analytic.line',
        string='Timesheet Entry',
        ondelete='set null',
        copy=False,
        help='Link to the corresponding hr.timesheet entry when timesheet '
             'module is active.',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('hours', 'cost_per_hour')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.hours * rec.cost_per_hour

    # ────────────────────────────────────────────────────────────────────────
    # Validation
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('job_order_id')
    def _check_job_order(self):
        for rec in self:
            if not rec.job_order_id:
                raise ValidationError(
                    _('Labour entry requires a Job Order.')
                )

    # ────────────────────────────────────────────────────────────────────────
    # ORM: auto-fill cost from employee
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Pull the employee's hourly rate as default cost_per_hour."""
        if self.employee_id and not self.cost_per_hour:
            contract = self.employee_id.sudo().contract_id
            if contract and contract.wage and contract.resource_calendar_id:
                # Approximate: monthly wage / monthly hours
                hours_per_month = (
                    contract.resource_calendar_id.hours_per_week * 4.33
                )
                if hours_per_month:
                    self.cost_per_hour = contract.wage / hours_per_month
