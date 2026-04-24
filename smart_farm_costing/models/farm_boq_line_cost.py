from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FarmBoqLineCost(models.Model):
    """Unified cost entry line for a BOQ subitem.

    One record per cost item, classified by ``job_type``.
    Each tab on the subitem form uses a separate One2many field filtered to its
    own job_type, so a line stored with job_type='labour' is physically stored
    once and displayed exclusively in the Labours tab.

    job_type values
    ---------------
    material      → Materials tab
    labour        → Labours tab
    subcontractor → Subcontractor tab
    tools         → Tools tab
    equipment     → Equipment tab
    other         → Others tab
    """

    _name = 'farm.boq.line.cost'
    _description = 'BOQ Line Cost Entry'
    _order = 'job_type, id'

    boq_line_id = fields.Many2one(
        comodel_name='farm.boq.line',
        string='BOQ Line',
        required=True,
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='boq_line_id.currency_id',
        store=False,
    )

    job_type = fields.Selection(
        selection=[
            ('material',      'Material'),
            ('labour',        'Labour'),
            ('subcontractor', 'Subcontractor'),
            ('tools',         'Tools'),
            ('equipment',     'Equipment'),
            ('other',         'Other'),
        ],
        string='Job Type',
        required=True,
        default='material',
        index=True,
    )

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        ondelete='set null',
    )
    description = fields.Char(string='Description', required=True)
    uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string='Unit',
        ondelete='restrict',
    )
    # ── Template ratio (set when line was created from a template) ───────────
    base_ratio_qty = fields.Float(
        string='Base Ratio',
        digits=(16, 4),
        default=0.0,
        help=(
            'Per-unit quantity from the BOQ template.\n'
            'When > 0: Quantity = Parent BOQ Qty × Base Ratio.\n'
            'Auto-set on template insert; zero for manually added lines.'
        ),
    )

    quantity   = fields.Float(string='Quantity',  default=1.0)
    unit_cost  = fields.Float(string='Unit Cost')
    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_total_cost',
        store=True,
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('quantity', 'unit_cost')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.quantity * rec.unit_cost

    # ────────────────────────────────────────────────────────────────────────
    # Onchange
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            # Always sync description, unit and rate from product
            self.description = self.product_id.name
            self.unit_cost   = self.product_id.standard_price
            self.uom_id      = self.product_id.uom_id
            # Auto-set job_type from product — ensures line matches product type
            if self.product_id.job_type:
                self.job_type = self.product_id.job_type
        else:
            self.uom_id = False

    # ────────────────────────────────────────────────────────────────────────
    # Validation
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('product_id', 'job_type')
    def _check_job_type_vs_product(self):
        """Ensure line job_type matches the selected product's job_type."""
        for rec in self:
            if rec.product_id and rec.product_id.job_type:
                if rec.product_id.job_type != rec.job_type:
                    raise ValidationError(
                        'Product "%s" has job type "%s" but this cost line '
                        'has job type "%s". They must match.'
                        % (rec.product_id.name, rec.product_id.job_type, rec.job_type)
                    )
