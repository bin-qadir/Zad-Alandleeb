from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FarmJobProgressLog(models.Model):
    """Incremental progress log for a Job Order.

    Each entry records a field-session increment: who reported how much was
    executed on a given date and any site notes.  The entries are informational
    (audit trail); the authoritative executed_qty lives on the Job Order itself.

    Auto-sync: whenever a log is created, edited, or deleted the parent
    Job Order's executed_qty is automatically updated to the sum of all
    log increments.  The manual "Sync from Logs" button remains available
    as an explicit re-sync trigger.
    """

    _name = 'farm.job.progress.log'
    _description = 'Job Order Progress Log'
    _order = 'job_order_id, date desc, id desc'
    _rec_name = 'display_name'

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

    # ── Log entry ─────────────────────────────────────────────────────────────
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
        index=True,
    )
    executed_increment = fields.Float(
        string='Qty Executed (this session)',
        digits=(16, 2),
        required=True,
        default=0.0,
        help='The quantity executed during this reporting session. '
             'Use "Sync Executed Qty" on the Job Order to roll all logs up.',
    )
    note = fields.Text(string='Site Note')
    logged_by = fields.Many2one(
        'res.users',
        string='Logged By',
        default=lambda self: self.env.user,
        readonly=True,
        index=True,
    )

    # ── Computed display name ──────────────────────────────────────────────────
    display_name = fields.Char(
        string='Log Entry',
        compute='_compute_display_name',
        store=True,
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('date', 'executed_increment', 'job_order_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s — %s (+%.2f)' % (
                rec.job_order_id.name or '',
                rec.date or '',
                rec.executed_increment,
            )

    # ────────────────────────────────────────────────────────────────────────
    # Validation
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('executed_increment')
    def _check_increment(self):
        for rec in self:
            if rec.executed_increment < 0:
                raise ValidationError(
                    _('Executed increment cannot be negative.')
                )

    # ────────────────────────────────────────────────────────────────────────
    # ORM — auto-sync parent JO executed_qty
    # ────────────────────────────────────────────────────────────────────────

    def _sync_job_order_executed_qty(self):
        """Update the parent Job Order executed_qty = sum of all log increments.

        Called after create / write / unlink so the JO always reflects the
        accumulated reported progress.
        """
        for jo in self.mapped('job_order_id'):
            total = sum(jo.progress_log_ids.mapped('executed_increment'))
            if jo.executed_qty != total:
                jo.sudo().write({'executed_qty': total})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_job_order_executed_qty()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'executed_increment' in vals:
            self._sync_job_order_executed_qty()
        return result

    def unlink(self):
        job_orders = self.mapped('job_order_id')
        result = super().unlink()
        # Re-sync after deletion (self is gone, use job_orders directly)
        for jo in job_orders:
            total = sum(jo.progress_log_ids.mapped('executed_increment'))
            if jo.executed_qty != total:
                jo.sudo().write({'executed_qty': total})
        return result
