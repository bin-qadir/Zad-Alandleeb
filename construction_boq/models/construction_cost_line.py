from odoo import api, fields, models

COST_TYPE_SELECTION = [
    ('material',    'Material'),
    ('labor',       'Labor'),
    ('subcontract', 'Subcontract'),
    ('equipment',   'Equipment'),
    ('tools',       'Tools'),
    ('overhead',    'Overhead'),
    ('other',       'Other'),
]


class ConstructionCostLine(models.Model):
    _name = 'construction.cost.line'
    _description = 'BOQ Cost Structure Line'
    _order = 'cost_type, sequence, id'

    # ── Parent ────────────────────────────────────────────────────────────────

    boq_line_id = fields.Many2one(
        comodel_name='construction.boq.line',
        string='BOQ Line',
        required=True,
        ondelete='cascade',
        index=True,
    )
    # Stored for easy search/grouping without joining through boq_line
    boq_id = fields.Many2one(
        comodel_name='construction.boq',
        string='BOQ',
        related='boq_line_id.boq_id',
        store=True,
        readonly=True,
        index=True,
    )
    project_id = fields.Many2one(
        comodel_name='construction.project',
        string='Project',
        related='boq_line_id.project_id',
        store=True,
        readonly=True,
        index=True,
    )

    # ── Classification ────────────────────────────────────────────────────────

    cost_type = fields.Selection(
        selection=COST_TYPE_SELECTION,
        string='Cost Type',
        required=True,
        default='material',
    )
    sequence = fields.Integer(string='Sequence', default=10)

    # ── Product / Description ─────────────────────────────────────────────────

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product / Resource',
        ondelete='set null',
    )
    description = fields.Char(
        string='Description',
        required=True,
    )
    unit = fields.Char(string='Unit', size=20)

    # ── Quantity & Cost ────────────────────────────────────────────────────────

    qty = fields.Float(
        string='Qty',
        default=1.0,
        digits=(16, 4),
    )
    unit_cost = fields.Float(
        string='Unit Cost',
        digits=(16, 4),
    )
    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_total_cost',
        store=True,
        digits=(16, 4),
    )

    # ── Notes ─────────────────────────────────────────────────────────────────

    notes = fields.Char(string='Notes')

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('qty', 'unit_cost')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.qty * rec.unit_cost

    # ── Onchange helpers ──────────────────────────────────────────────────────

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Pull description and unit from product when set."""
        if self.product_id:
            self.description = self.product_id.display_name
            if self.product_id.uom_id:
                self.unit = self.product_id.uom_id.name
            if not self.unit_cost and self.product_id.standard_price:
                self.unit_cost = self.product_id.standard_price
