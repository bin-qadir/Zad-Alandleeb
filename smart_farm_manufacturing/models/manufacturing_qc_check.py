from odoo import api, fields, models, _


class ManufacturingQCCheck(models.Model):
    """Quality Control Check — inspect a work order's output."""

    _name = 'manufacturing.qc.check'
    _description = 'Manufacturing QC Check'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'check_date desc, name'
    _rec_name = 'name'

    name = fields.Char(string='QC Reference', required=True, tracking=True)

    # ── Context ───────────────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        related='work_order_id.company_id',
        store=True,
        readonly=True,
    )
    work_order_id = fields.Many2one(
        comodel_name='manufacturing.work.order',
        string='Work Order',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    plan_id = fields.Many2one(
        comodel_name='manufacturing.plan',
        related='work_order_id.plan_id',
        store=True,
        readonly=True,
        string='Production Plan',
    )

    # ── Check Details ─────────────────────────────────────────────────────────

    check_date = fields.Date(string='Check Date', default=fields.Date.today, tracking=True)
    inspector_id = fields.Many2one(
        comodel_name='res.users',
        string='Inspector',
        default=lambda self: self.env.user,
        tracking=True,
    )
    check_type = fields.Selection(
        selection=[
            ('visual',     'Visual Inspection'),
            ('weight',     'Weight Check'),
            ('dimension',  'Dimension Check'),
            ('functional', 'Functional Test'),
            ('chemical',   'Chemical Analysis'),
            ('other',      'Other'),
        ],
        string='Check Type',
        required=True,
        default='visual',
    )

    # ── Result ────────────────────────────────────────────────────────────────

    result = fields.Selection(
        selection=[
            ('pass',    'Pass'),
            ('fail',    'Fail'),
            ('rework',  'Rework Required'),
            ('pending', 'Pending'),
        ],
        string='Result',
        default='pending',
        required=True,
        tracking=True,
    )
    sample_qty = fields.Float(string='Sample Quantity', digits=(16, 2))
    pass_qty = fields.Float(string='Accepted Qty', digits=(16, 2))
    fail_qty = fields.Float(string='Rejected Qty', digits=(16, 2))
    defect_description = fields.Text(string='Defect Description')
    corrective_action = fields.Text(string='Corrective Action')

    state = fields.Selection(
        selection=[
            ('draft',    'Draft'),
            ('checking', 'Checking'),
            ('done',     'Done'),
        ],
        default='draft',
        required=True,
        tracking=True,
    )
    notes = fields.Text(string='Notes')

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_start_check(self):
        self.write({'state': 'checking'})

    def action_pass(self):
        self.write({'state': 'done', 'result': 'pass'})

    def action_fail(self):
        self.write({'state': 'done', 'result': 'fail'})

    def action_rework(self):
        self.write({'state': 'done', 'result': 'rework'})
