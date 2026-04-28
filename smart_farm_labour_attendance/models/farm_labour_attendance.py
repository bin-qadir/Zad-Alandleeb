"""
farm.labour.attendance — Daily Field Labour Attendance Sheet
=============================================================

One sheet per project/division/date.  Records which workers were present,
their check-in/check-out times, GPS coordinates, and signatures.

Workflow:
  draft → open → closed
  open/draft → cancelled → draft (reset)

On Close Day:
  For every line with attendance_state='present', if a job_order_id is linked,
  a farm.labour.entry record is created (or updated if already exists for
  this attendance line).  No labour entry is created for absent/late/leave
  workers, preserving the absence audit trail.

GPS and signature fields are manually editable.  Browser-side GPS capture
can be added via future JS actions.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FarmLabourAttendance(models.Model):
    """Daily labour attendance sheet — one per project/division/date."""

    _name        = 'farm.labour.attendance'
    _description = 'Daily Labour Attendance'
    _order       = 'date desc, id desc'
    _rec_name    = 'name'
    _inherit     = ['mail.thread', 'mail.activity.mixin']

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        default=lambda self: _('New'),
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
        index=True,
    )

    # ── Project scope ─────────────────────────────────────────────────────────
    project_id = fields.Many2one(
        'farm.project',
        string='Project',
        required=True,
        ondelete='restrict',
        tracking=True,
        index=True,
    )
    division_id = fields.Many2one(
        'farm.division.work',
        string='Division',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    subdivision_id = fields.Many2one(
        'farm.subdivision.work',
        string='Subdivision',
        ondelete='restrict',
        domain="[('division_id', '=', division_id)]",
    )
    boq_line_id = fields.Many2one(
        'farm.boq.line',
        string='Main BOQ Item',
        ondelete='restrict',
        domain="[('display_type', '=', False)]",
    )
    sub_boq_line_id = fields.Many2one(
        'farm.boq.line',
        string='Sub BOQ Item',
        ondelete='restrict',
        domain="[('display_type', '=', False)]",
    )
    job_order_id = fields.Many2one(
        'farm.job.order',
        string='Job Order',
        ondelete='restrict',
        domain="[('project_id', '=', project_id)]",
        tracking=True,
        help=(
            'Link a Job Order to automatically create Labour Entry records '
            'for present workers when closing the day.\n'
            'farm.labour.entry requires a job order — without one, '
            'no entries are generated.'
        ),
    )

    # ── Responsible ───────────────────────────────────────────────────────────
    responsible_user_id = fields.Many2one(
        'res.users',
        string='Responsible (User)',
        default=lambda self: self.env.user,
        index=True,
        tracking=True,
    )
    responsible_employee_id = fields.Many2one(
        'hr.employee',
        string='Responsible Employee',
        ondelete='set null',
    )

    # ── Workflow state ────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft',     'Draft'),
            ('open',      'Open'),
            ('closed',    'Closed'),
            ('cancelled', 'Cancelled'),
        ],
        string='State',
        default='draft',
        required=True,
        index=True,
        tracking=True,
        copy=False,
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    check_in_open_time  = fields.Datetime(string='Opened At',  readonly=True, copy=False)
    check_out_close_time = fields.Datetime(string='Closed At', readonly=True, copy=False)

    # ── Supervisor GPS ────────────────────────────────────────────────────────
    supervisor_gps_lat     = fields.Float(string='Supervisor Latitude',  digits=(10, 7))
    supervisor_gps_lng     = fields.Float(string='Supervisor Longitude', digits=(10, 7))
    supervisor_gps_address = fields.Char(string='Supervisor Location')

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(string='Notes / ملاحظات')

    # ── Lines ─────────────────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'farm.labour.attendance.line',
        'attendance_id',
        string='Workers',
    )

    # ── Computed KPIs ─────────────────────────────────────────────────────────
    worker_count = fields.Integer(
        string='Worker Count',
        compute='_compute_kpis',
        store=True,
    )
    present_count = fields.Integer(
        string='Present',
        compute='_compute_kpis',
        store=True,
    )
    absent_count = fields.Integer(
        string='Absent',
        compute='_compute_kpis',
        store=True,
    )
    total_hours = fields.Float(
        string='Total Hours',
        compute='_compute_kpis',
        store=True,
        digits=(16, 2),
    )
    total_labour_cost = fields.Float(
        string='Total Labour Cost',
        compute='_compute_kpis',
        store=True,
        digits=(16, 2),
    )
    labour_entry_count = fields.Integer(
        string='Labour Entries',
        compute='_compute_labour_entry_count',
    )

    @api.depends(
        'line_ids.attendance_state',
        'line_ids.hours',
        'line_ids.total_cost',
    )
    def _compute_kpis(self):
        for rec in self:
            lines   = rec.line_ids
            present = lines.filtered(lambda l: l.attendance_state == 'present')
            rec.worker_count      = len(lines)
            rec.present_count     = len(present)
            rec.absent_count      = len(lines.filtered(lambda l: l.attendance_state == 'absent'))
            rec.total_hours       = sum(present.mapped('hours'))
            rec.total_labour_cost = sum(present.mapped('total_cost'))

    def _compute_labour_entry_count(self):
        for rec in self:
            rec.labour_entry_count = self.env['farm.labour.entry'].sudo().search_count([
                ('attendance_id', '=', rec.id),
            ])

    # ── ORM ───────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = seq.next_by_code('farm.labour.attendance') or _('New')
        return super().create(vals_list)

    # ── Workflow actions ──────────────────────────────────────────────────────

    def action_open(self):
        """Open the attendance sheet — workers can now be marked present/absent."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft attendance sheets can be opened.'))
        self.write({
            'state':              'open',
            'check_in_open_time': fields.Datetime.now(),
        })

    def action_close_day(self):
        """Close the day and auto-create Labour Entry records for present workers.

        Labour entries are only created when a Job Order is linked.
        Workers with attendance_state != 'present' are NOT given entries —
        their record is kept for the absence audit trail.
        """
        for rec in self:
            if rec.state != 'open':
                raise UserError(_('Only open attendance sheets can be closed.'))
            rec._create_or_update_labour_entries()
        self.write({
            'state':               'closed',
            'check_out_close_time': fields.Datetime.now(),
        })

    def action_cancel(self):
        """Cancel the attendance sheet."""
        for rec in self:
            if rec.state == 'closed':
                raise UserError(_('Closed attendance sheets cannot be cancelled.'))
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        """Reset a cancelled sheet back to draft."""
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_('Only cancelled sheets can be reset.'))
        self.write({'state': 'draft'})

    def action_create_labour_entries(self):
        """Manually trigger Labour Entry creation (idempotent — safe to run again)."""
        for rec in self:
            if not rec.job_order_id:
                raise UserError(_(
                    'Cannot create Labour Entries: no Job Order linked.\n\n'
                    'Link a Job Order in the "Project Scope" section first.'
                ))
            if rec.state not in ('open', 'closed'):
                raise UserError(_(
                    'Attendance sheet must be open or closed to create labour entries.'
                ))
            rec._create_or_update_labour_entries()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _create_or_update_labour_entries(self):
        """Upsert farm.labour.entry for each present worker.

        Idempotent: if an entry already exists for the attendance line,
        it is updated rather than duplicated.
        """
        self.ensure_one()
        if not self.job_order_id:
            return   # silently skip — not an error in batch context

        LE           = self.env['farm.labour.entry']
        present_lines = self.line_ids.filtered(lambda l: l.attendance_state == 'present')

        for line in present_lines:
            vals = {
                'job_order_id':       self.job_order_id.id,
                'employee_id':        line.employee_id.id,
                'date':               self.date,
                'hours':              max(line.hours, 0.01),    # avoid 0-hour entries
                'cost_per_hour':      line.hourly_rate or 0.0,
                'description':        _('Attendance %s · %s · %s') % (
                                          self.name, self.date, line.employee_id.name
                                      ),
                'attendance_id':      self.id,
                'attendance_line_id': line.id,
                'check_in':           line.check_in,
                'check_out':          line.check_out,
                'worker_signature':   line.worker_signature,
                'worker_gps_lat':     line.worker_gps_lat,
                'worker_gps_lng':     line.worker_gps_lng,
            }
            existing = LE.search([('attendance_line_id', '=', line.id)], limit=1)
            if existing:
                existing.write(vals)
            else:
                LE.create(vals)

    # ── Smart-button actions ──────────────────────────────────────────────────

    def action_view_labour_entries(self):
        """Show Labour Entries linked to this attendance sheet."""
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Labour Entries — %s') % self.name,
            'res_model': 'farm.labour.entry',
            'view_mode': 'list,form',
            'domain':    [('attendance_id', '=', self.id)],
            'context':   {'default_attendance_id': self.id},
        }

    def action_add_workers(self):
        """Open the Add Workers wizard for quick multi-worker selection."""
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Add Workers / إضافة عمال'),
            'res_model': 'farm.labour.attendance.add.workers.wizard',
            'view_mode': 'form',
            'target':    'new',
            'context': {
                'default_attendance_id': self.id,
                'default_project_id':    self.project_id.id,
                'default_division_id':   self.division_id.id if self.division_id else False,
            },
        }
