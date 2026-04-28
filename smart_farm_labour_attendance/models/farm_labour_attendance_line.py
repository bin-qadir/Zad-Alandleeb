"""
farm.labour.attendance.line — Per-worker line of a daily attendance sheet.
==========================================================================

One line per employee per attendance sheet.  Tracks:
  • Attendance state: present / absent / late / on leave
  • Check-in / check-out times (hours auto-computed)
  • Hourly rate and total cost
  • Worker signature (binary)
  • Worker GPS coordinates
  • Supervisor GPS coordinates at the time of sign-off

Closed sheet write-protection:
  Normal users cannot edit lines on closed sheets.
  Execution Managers can always write.
"""
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FarmLabourAttendanceLine(models.Model):
    """One attendance record per worker on a daily attendance sheet."""

    _name        = 'farm.labour.attendance.line'
    _description = 'Labour Attendance Line'
    _order       = 'attendance_id, employee_id'
    _rec_name    = 'employee_id'

    # ── Links ─────────────────────────────────────────────────────────────────
    attendance_id = fields.Many2one(
        'farm.labour.attendance',
        string='Attendance Sheet',
        required=True,
        ondelete='cascade',
        index=True,
    )
    project_id = fields.Many2one(
        'farm.project',
        related='attendance_id.project_id',
        string='Project',
        store=True,
        readonly=True,
        index=True,
    )
    date = fields.Date(
        related='attendance_id.date',
        string='Date',
        store=True,
        readonly=True,
        index=True,
    )
    sheet_state = fields.Selection(
        related='attendance_id.state',
        string='Sheet State',
        store=False,
    )

    # ── Employee ──────────────────────────────────────────────────────────────
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='restrict',
        index=True,
    )
    mobile_phone = fields.Char(
        related='employee_id.mobile_phone',
        string='Mobile',
        readonly=True,
    )
    job_title = fields.Char(
        related='employee_id.job_title',
        string='Job Title',
        readonly=True,
    )

    # ── Attendance state ──────────────────────────────────────────────────────
    attendance_state = fields.Selection(
        selection=[
            ('present', 'Present'),
            ('absent',  'Absent'),
            ('late',    'Late'),
            ('leave',   'On Leave'),
        ],
        string='Status',
        default='present',
        required=True,
        index=True,
    )

    # ── Time tracking ─────────────────────────────────────────────────────────
    check_in  = fields.Datetime(string='Check In')
    check_out = fields.Datetime(string='Check Out')
    hours     = fields.Float(
        string='Hours',
        compute='_compute_hours',
        store=True,
        digits=(16, 2),
        help='Auto-calculated from check-in/check-out.',
    )

    # ── Cost ─────────────────────────────────────────────────────────────────
    hourly_rate = fields.Float(
        string='Rate / hr',
        digits=(16, 4),
        default=0.0,
    )
    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_total_cost',
        store=True,
        digits=(16, 2),
    )

    # ── Signature ─────────────────────────────────────────────────────────────
    worker_signature      = fields.Binary(string='Signature', attachment=True)
    worker_signature_date = fields.Datetime(string='Signed At')

    # ── Worker GPS ────────────────────────────────────────────────────────────
    worker_gps_lat     = fields.Float(string='Worker Lat',       digits=(10, 7))
    worker_gps_lng     = fields.Float(string='Worker Lng',       digits=(10, 7))
    worker_gps_address = fields.Char(string='Worker Location')

    # ── Supervisor GPS (captured at sign-off) ─────────────────────────────────
    supervisor_gps_lat = fields.Float(string='Supervisor Lat',   digits=(10, 7))
    supervisor_gps_lng = fields.Float(string='Supervisor Lng',   digits=(10, 7))

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Char(string='Notes')

    # ── Computed ──────────────────────────────────────────────────────────────

    @api.depends('check_in', 'check_out')
    def _compute_hours(self):
        for rec in self:
            if rec.check_in and rec.check_out and rec.check_out > rec.check_in:
                rec.hours = (rec.check_out - rec.check_in).total_seconds() / 3600.0
            else:
                rec.hours = 0.0

    @api.depends('hours', 'hourly_rate')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.hours * rec.hourly_rate

    # ── Onchange ──────────────────────────────────────────────────────────────

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Pre-fill hourly rate from the employee's active contract."""
        if self.employee_id and not self.hourly_rate:
            try:
                contract = self.employee_id.sudo().contract_id
                if contract and contract.wage and contract.resource_calendar_id:
                    hpm = contract.resource_calendar_id.hours_per_week * 4.33
                    if hpm:
                        self.hourly_rate = round(contract.wage / hpm, 4)
            except Exception:
                pass

    @api.onchange('worker_signature')
    def _onchange_worker_signature(self):
        """Auto-stamp signature date when a signature is captured."""
        if self.worker_signature and not self.worker_signature_date:
            self.worker_signature_date = fields.Datetime.now()

    # ── Validation ────────────────────────────────────────────────────────────

    @api.constrains('check_in', 'check_out')
    def _check_times(self):
        for rec in self:
            if rec.check_in and rec.check_out and rec.check_out <= rec.check_in:
                raise ValidationError(
                    _('Check-out must be after check-in.\nEmployee: %s') % rec.employee_id.name
                )

    # ── Write protection for closed sheets ────────────────────────────────────

    def write(self, vals):
        if not self.env.su:
            is_manager = self.env.user.has_group(
                'smart_farm_execution.group_smart_farm_execution_manager'
            )
            for rec in self:
                if rec.attendance_id.state == 'closed' and not is_manager:
                    raise ValidationError(
                        _('Attendance sheet "%s" is closed.\n'
                          'Only Execution Managers can edit closed sheets.')
                        % rec.attendance_id.name
                    )
        return super().write(vals)
