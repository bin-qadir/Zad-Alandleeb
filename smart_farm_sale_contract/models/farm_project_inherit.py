from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FarmProjectSaleContract(models.Model):
    """Extend farm.project with:

    1. currency_id     — from the company, for monetary widget support
    2. sale_order_count + action_open_sale_orders()
    3. Cost control fields:
       - estimated_cost    : sum of approved BOQ Analysis total_cost
       - contract_value    : sum of approved SO amount_untaxed
       - actual_material_cost / actual_labour_cost / actual_total_cost
       - cost_variance     : actual_total_cost - contract_value
    4. Override action_phase_to_execution() — accept EITHER
       an approved farm.contract OR an approved sale.order as the gate.

    Note: job_order_ids One2many is defined by smart_farm_execution
    (single source of truth). This module uses it in @api.depends only.
    """

    _inherit = 'farm.project'

    # ── Currency (from company) ───────────────────────────────────────────────

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True,
        store=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        ondelete='restrict',
    )

    # ── Sales Orders link ─────────────────────────────────────────────────────

    sale_order_count = fields.Integer(
        string='Sales Orders',
        compute='_compute_sale_order_count',
    )

    # ── Cost control ──────────────────────────────────────────────────────────

    estimated_cost = fields.Float(
        string='Estimated Cost',
        compute='_compute_project_costs',
        store=True,
        digits=(16, 2),
        help='Sum of total_cost from all approved BOQ Analyses for this project.',
    )

    contract_value = fields.Float(
        string='Contract Value',
        compute='_compute_project_costs',
        store=True,
        digits=(16, 2),
        help='Sum of amount_untaxed from all approved Sales Orders linked to this project.',
    )

    actual_material_cost = fields.Float(
        string='Actual Material Cost',
        compute='_compute_project_costs',
        store=True,
        digits=(16, 2),
        help='Sum of actual_material_cost from all Job Orders for this project.',
    )

    actual_labour_cost = fields.Float(
        string='Actual Labour Cost',
        compute='_compute_project_costs',
        store=True,
        digits=(16, 2),
        help='Sum of actual_labour_cost from all Job Orders for this project.',
    )

    actual_total_cost = fields.Float(
        string='Actual Total Cost',
        compute='_compute_project_costs',
        store=True,
        digits=(16, 2),
        help='Total of actual material + labour costs across all Job Orders.',
    )

    cost_variance = fields.Float(
        string='Cost Variance',
        compute='_compute_project_costs',
        store=True,
        digits=(16, 2),
        help=(
            'Actual Total Cost minus Contract Value.\n'
            'Positive = over contract budget.\n'
            'Negative = under contract budget.'
        ),
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    def _compute_sale_order_count(self):
        SaleOrder = self.env['sale.order']
        for rec in self:
            rec.sale_order_count = SaleOrder.search_count(
                [('farm_project_id', '=', rec.id)]
            )

    @api.depends(
        'job_order_ids.actual_material_cost',
        'job_order_ids.actual_labour_cost',
    )
    def _compute_project_costs(self):
        BoqAnalysis = self.env['farm.boq.analysis']
        SaleOrder = self.env['sale.order']

        for rec in self:
            # ── Estimated cost: approved BOQ analyses ─────────────────────────
            analyses = BoqAnalysis.search([
                ('project_id', '=', rec.id),
                ('analysis_state', '=', 'approved'),
            ])
            rec.estimated_cost = sum(analyses.mapped('total_cost'))

            # ── Contract value: approved sales orders ─────────────────────────
            approved_sos = SaleOrder.search([
                ('farm_project_id', '=', rec.id),
                ('is_contract_approved', '=', True),
            ])
            rec.contract_value = sum(approved_sos.mapped('amount_untaxed'))

            # ── Actual costs from Job Orders ──────────────────────────────────
            mat = sum(rec.job_order_ids.mapped('actual_material_cost'))
            lab = sum(rec.job_order_ids.mapped('actual_labour_cost'))
            rec.actual_material_cost = mat
            rec.actual_labour_cost   = lab
            rec.actual_total_cost    = mat + lab

            # ── Variance: actual minus contract ───────────────────────────────
            rec.cost_variance = rec.actual_total_cost - rec.contract_value

    # ────────────────────────────────────────────────────────────────────────
    # Navigation
    # ────────────────────────────────────────────────────────────────────────

    def action_open_sale_orders(self):
        """Open all Sales Orders linked to this project."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sales Orders — %s') % self.name,
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('farm_project_id', '=', self.id)],
            'context': {
                'default_farm_project_id': self.id,
            },
        }

    # ────────────────────────────────────────────────────────────────────────
    # Phase gate — combined: farm.contract OR sale.order approval
    # ────────────────────────────────────────────────────────────────────────

    def action_phase_to_execution(self):
        """Contract → Execution.

        GATE (either is sufficient):
        • At least one farm.contract in state 'approved' or 'active', OR
        • At least one sale.order with is_contract_approved = True
          linked to this project.

        This overrides smart_farm_contract's version (which only checks
        farm.contract) to also accept an approved sales order.
        """
        for rec in self.filtered(lambda r: r.project_phase == 'contract'):

            # Gate 1: approved farm.contract
            approved_contract = rec.contract_ids.filtered(
                lambda c: c.state in ('approved', 'active')
            )

            # Gate 2: approved sale.order
            approved_so = self.env['sale.order'].search([
                ('farm_project_id', '=', rec.id),
                ('is_contract_approved', '=', True),
            ], limit=1)

            if not approved_contract and not approved_so:
                raise UserError(_(
                    'Cannot move project "%(name)s" to Execution phase.\n\n'
                    'An approved contract is required. Either:\n'
                    '  • Approve a Farm Contract linked to this project, OR\n'
                    '  • Approve a Sales Order (set Contract Stage → Approved) '
                    'linked to this project.\n\n'
                    'Open Contracts or Sales Orders from this project form.',
                    name=rec.name,
                ))
            rec.project_phase = 'execution'
