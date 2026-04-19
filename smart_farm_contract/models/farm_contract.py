from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FarmContract(models.Model):
    """Farm Contract — gate between BOQ Analysis approval and Job Order execution.

    Workflow:
        draft → review → approved → active → closed

    A contract in state 'approved' or 'active' is required before
    Job Orders can be generated for the linked project.
    """

    _name = 'farm.contract'
    _description = 'Farm Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Contract Reference',
        required=True,
        copy=False,
        default=lambda self: _('New'),
        tracking=True,
    )

    # ── Core links ────────────────────────────────────────────────────────────
    project_id = fields.Many2one(
        'farm.project',
        string='Farm Project',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
    )
    boq_id = fields.Many2one(
        'farm.boq',
        string='BOQ Document',
        domain="[('project_id', '=', project_id)]",
        ondelete='restrict',
        index=True,
        tracking=True,
    )
    boq_analysis_id = fields.Many2one(
        'farm.boq.analysis',
        string='BOQ Analysis',
        domain="[('project_id', '=', project_id)]",
        ondelete='set null',
        index=True,
        tracking=True,
    )

    # ── Financial ─────────────────────────────────────────────────────────────
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        ondelete='restrict',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True,
        store=True,
    )
    contract_amount = fields.Float(
        string='Contract Amount',
        digits=(16, 2),
        tracking=True,
        help='Total agreed contract value.',
    )
    contract_qty = fields.Float(
        string='Contract Quantity',
        digits=(16, 2),
        help='Overall contracted quantity (scope reference).',
    )

    # ── Dates ─────────────────────────────────────────────────────────────────
    date_start = fields.Date(string='Start Date', tracking=True)
    date_end   = fields.Date(string='End Date',   tracking=True)
    date_signed = fields.Date(string='Date Signed', copy=False)

    # ── Workflow state ────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft',    'Draft'),
            ('review',   'Under Review'),
            ('approved', 'Approved'),
            ('active',   'Active'),
            ('closed',   'Closed'),
        ],
        string='Status',
        default='draft',
        required=True,
        index=True,
        copy=False,
        tracking=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(string='Contract Notes / Scope')

    # ── Stat button ───────────────────────────────────────────────────────────
    job_order_count = fields.Integer(
        string='Job Orders',
        compute='_compute_job_order_count',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    def _compute_job_order_count(self):
        JobOrder = self.env['farm.job.order']
        for rec in self:
            rec.job_order_count = JobOrder.search_count(
                [('contract_id', '=', rec.id)]
            )

    # ────────────────────────────────────────────────────────────────────────
    # ORM
    # ────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('from_sale_contract_approved'):
            raise UserError(_(
                'Contracts cannot be created manually.\n\n'
                'Open an approved Sale Order and click "Create Contract" '
                'to generate the contract automatically.'
            ))
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = seq.next_by_code('farm.contract') or _('New')
        return super().create(vals_list)

    # ────────────────────────────────────────────────────────────────────────
    # State machine
    # ────────────────────────────────────────────────────────────────────────

    def action_submit_review(self):
        """Draft → Under Review."""
        for rec in self.filtered(lambda r: r.state == 'draft'):
            if not rec.project_id:
                raise UserError(_('A project must be linked before submitting for review.'))
            rec.state = 'review'

    def action_approve(self):
        """Review → Approved."""
        for rec in self.filtered(lambda r: r.state == 'review'):
            rec.write({'state': 'approved'})

    def action_activate(self):
        """Approved → Active.  Records the signed date if not already set."""
        for rec in self.filtered(lambda r: r.state == 'approved'):
            vals = {'state': 'active'}
            if not rec.date_signed:
                vals['date_signed'] = fields.Date.today()
            rec.write(vals)

    def action_close(self):
        """Active → Closed."""
        for rec in self.filtered(lambda r: r.state == 'active'):
            rec.state = 'closed'

    def action_reset_draft(self):
        """Review → Draft (correction)."""
        self.filtered(lambda r: r.state == 'review').write({'state': 'draft'})

    # ────────────────────────────────────────────────────────────────────────
    # Navigation actions (stat buttons)
    # ────────────────────────────────────────────────────────────────────────

    def action_open_boq(self):
        self.ensure_one()
        if not self.boq_id:
            raise UserError(_('No BOQ Document linked to this contract.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQ Document — %s') % self.boq_id.name,
            'res_model': 'farm.boq',
            'view_mode': 'form',
            'res_id': self.boq_id.id,
        }

    def action_open_analysis(self):
        self.ensure_one()
        if not self.boq_analysis_id:
            raise UserError(_('No BOQ Analysis linked to this contract.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQ Analysis — %s') % self.boq_analysis_id.name,
            'res_model': 'farm.boq.analysis',
            'view_mode': 'form',
            'res_id': self.boq_analysis_id.id,
        }

    def action_open_job_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Job Orders — %s') % self.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {
                'default_contract_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }
