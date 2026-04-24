from odoo import api, fields, models, _


class ManufacturingWorkOrder(models.Model):
    """Work Order — a discrete production run within a plan."""

    _name = 'manufacturing.work.order'
    _description = 'Manufacturing Work Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, planned_date, name'
    _rec_name = 'name'

    name = fields.Char(string='Work Order', required=True, tracking=True)
    sequence = fields.Integer(string='Sequence', default=10)

    # ── Context ───────────────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        related='plan_id.company_id',
        store=True,
        readonly=True,
    )
    plan_id = fields.Many2one(
        comodel_name='manufacturing.plan',
        string='Production Plan',
        required=True,
        ondelete='cascade',
        tracking=True,
    )

    # ── Product ───────────────────────────────────────────────────────────────

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product / Component',
        ondelete='set null',
        tracking=True,
    )
    planned_qty = fields.Float(string='Planned Qty', digits=(16, 2))
    actual_qty = fields.Float(string='Actual Qty', digits=(16, 2))
    uom_id = fields.Many2one(comodel_name='uom.uom', string='Unit', ondelete='set null')
    work_type_id = fields.Many2one(
        comodel_name='farm.work.type',
        string='Work Type',
        ondelete='set null',
    )

    # ── Schedule ──────────────────────────────────────────────────────────────

    planned_date = fields.Date(string='Planned Date', tracking=True)
    actual_date = fields.Date(string='Actual Date')
    planned_duration_hours = fields.Float(string='Planned Hours', digits=(8, 2))
    actual_duration_hours = fields.Float(string='Actual Hours', digits=(8, 2))

    # ── Resources ─────────────────────────────────────────────────────────────

    operator_id = fields.Many2one(
        comodel_name='res.users',
        string='Operator',
    )
    workcenter = fields.Char(string='Workcenter / Line')

    # ── Costs ──────────────────────────────────────────────────────────────────

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    estimated_cost = fields.Monetary(string='Estimated Cost', currency_field='currency_id')
    actual_cost = fields.Monetary(string='Actual Cost', currency_field='currency_id')

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',       'Draft'),
            ('ready',       'Ready'),
            ('in_progress', 'In Progress'),
            ('done',        'Done'),
            ('cancelled',   'Cancelled'),
        ],
        default='draft',
        required=True,
        tracking=True,
    )

    # ── QC ────────────────────────────────────────────────────────────────────

    qc_check_ids = fields.One2many(
        comodel_name='manufacturing.qc.check',
        inverse_name='work_order_id',
        string='QC Checks',
    )
    qc_check_count = fields.Integer(compute='_compute_qc_count', store=False)
    qc_result = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('pass',    'Pass'),
            ('fail',    'Fail'),
        ],
        string='QC Result',
        default='pending',
        tracking=True,
    )

    notes = fields.Text(string='Notes')

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('qc_check_ids')
    def _compute_qc_count(self):
        for rec in self:
            rec.qc_check_count = len(rec.qc_check_ids)

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_set_ready(self):
        self.write({'state': 'ready'})

    def action_start(self):
        self.write({'state': 'in_progress', 'actual_date': fields.Date.today()})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_view_qc_checks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('QC Checks'),
            'res_model': 'manufacturing.qc.check',
            'view_mode': 'list,form',
            'domain': [('work_order_id', '=', self.id)],
            'context': {'default_work_order_id': self.id},
        }
