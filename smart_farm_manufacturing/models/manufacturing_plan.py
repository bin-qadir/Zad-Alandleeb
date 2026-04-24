from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


BUSINESS_ACTIVITY = 'manufacturing'


class ManufacturingPlan(models.Model):
    """Production plan — master plan for a manufacturing cycle."""

    _name = 'manufacturing.plan'
    _description = 'Manufacturing Production Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'planned_start desc, name'
    _rec_name = 'name'

    name = fields.Char(string='Plan Name', required=True, tracking=True)
    reference = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        index=True,
        tracking=True,
    )

    # ── Company & Activity ────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    business_activity = fields.Selection(
        selection=[
            ('construction',  'Construction'),
            ('agriculture',   'Agriculture'),
            ('manufacturing', 'Manufacturing'),
            ('livestock',     'Livestock'),
        ],
        default=BUSINESS_ACTIVITY,
        readonly=True,
        store=True,
    )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    lifecycle_stage_id = fields.Many2one(
        comodel_name='activity.lifecycle.stage',
        string='Lifecycle Stage',
        domain=[('business_activity', '=', BUSINESS_ACTIVITY)],
        ondelete='set null',
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft',       'Draft'),
            ('confirmed',   'Confirmed'),
            ('in_progress', 'In Progress'),
            ('done',        'Completed'),
            ('cancelled',   'Cancelled'),
        ],
        default='draft',
        required=True,
        tracking=True,
    )

    # ── Links ─────────────────────────────────────────────────────────────────

    farm_project_id = fields.Many2one(
        comodel_name='farm.project',
        string='Project',
        domain=[('business_activity', '=', BUSINESS_ACTIVITY)],
        ondelete='set null',
        tracking=True,
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        ondelete='set null',
    )
    responsible_id = fields.Many2one(
        comodel_name='res.users',
        string='Production Manager',
        default=lambda self: self.env.user,
        tracking=True,
    )

    # ── Schedule ──────────────────────────────────────────────────────────────

    planned_start = fields.Date(string='Planned Start', tracking=True)
    planned_end = fields.Date(string='Planned End', tracking=True)
    actual_start = fields.Date(string='Actual Start')
    actual_end = fields.Date(string='Actual End')

    # ── Product ───────────────────────────────────────────────────────────────

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Finished Product',
        ondelete='set null',
        tracking=True,
    )
    planned_qty = fields.Float(string='Planned Quantity', digits=(16, 2))
    uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string='Unit of Measure',
        ondelete='set null',
    )

    # ── Financials ────────────────────────────────────────────────────────────

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    budgeted_cost = fields.Monetary(string='Budgeted Cost', currency_field='currency_id')
    actual_cost = fields.Monetary(
        string='Actual Cost',
        compute='_compute_actual_cost',
        store=True,
        currency_field='currency_id',
    )

    # ── AI Decision Layer ─────────────────────────────────────────────────────

    risk_score = fields.Float(string='Risk Score', default=0.0, digits=(5, 1))
    delay_score = fields.Float(string='Delay Score', default=0.0, digits=(5, 1))
    budget_risk = fields.Float(string='Budget Risk', default=0.0, digits=(5, 1))
    claim_readiness = fields.Float(string='Claim Readiness', default=0.0, digits=(5, 1))
    next_recommended_action = fields.Text(string='Next Recommended Action')

    # ── Children ──────────────────────────────────────────────────────────────

    work_order_ids = fields.One2many(
        comodel_name='manufacturing.work.order',
        inverse_name='plan_id',
        string='Work Orders',
    )
    work_order_count = fields.Integer(compute='_compute_counts', store=False)

    notes = fields.Text(string='Notes')

    # ── SQL Constraints ───────────────────────────────────────────────────────

    _sql_constraints = [
        ('unique_ref_company', 'UNIQUE(reference, company_id)',
         'A production plan with this reference already exists for this company.'),
    ]

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('work_order_ids', 'work_order_ids.actual_cost')
    def _compute_actual_cost(self):
        for rec in self:
            rec.actual_cost = sum(rec.work_order_ids.mapped('actual_cost'))

    @api.depends('work_order_ids')
    def _compute_counts(self):
        for rec in self:
            rec.work_order_count = len(rec.work_order_ids)

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_start(self):
        self.write({'state': 'in_progress', 'actual_start': fields.Date.today()})

    def action_complete(self):
        self.write({'state': 'done', 'actual_end': fields.Date.today()})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_view_work_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Work Orders'),
            'res_model': 'manufacturing.work.order',
            'view_mode': 'list,form',
            'domain': [('plan_id', '=', self.id)],
            'context': {'default_plan_id': self.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('reference'):
                vals['reference'] = self.env['ir.sequence'].next_by_code(
                    'manufacturing.plan') or '/'
        return super().create(vals_list)
