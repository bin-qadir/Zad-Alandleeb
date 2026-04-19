from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FarmBoqLineTemplate(models.Model):
    """Standalone BOQ Item Template — mirrors farm.boq.line with full costing breakdown.

    Each template represents a single reusable BOQ item (not a collection / header).
    Use the 'Create BOQ Line' button to instantiate it into a real BOQ document.

    Ordered by Division → Subdivision → Name for consistent, predictable listing.
    Template names must be unique within the same Division + Subdivision scope.

    Resource tabs and their allowed product types:
      Materials     — Storable / Consumable / Service
      Labour        — Service only
      Subcontractor — Service only
      Equipment     — Service only
      Tools         — Service only
      Others        — Service only (was: Overhead; backward-compatible)
    """

    _name = 'farm.boq.line.template'
    _description = 'BOQ Item Template'
    _order = 'division_id, subdivision_id, name'

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')

    # ── Classification ────────────────────────────────────────────────────────
    division_id = fields.Many2one(
        'farm.division.work', string='Division', ondelete='set null',
    )
    subdivision_id = fields.Many2one(
        'farm.subdivision.work', string='Subdivision', ondelete='set null',
        domain="[('division_id', '=', division_id)]",
    )

    # ── Company / Currency ────────────────────────────────────────────────────
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='company_id.currency_id', store=True, readonly=True,
    )

    # ── Quantities & Pricing ──────────────────────────────────────────────────
    quantity = fields.Float(string='Quantity', default=1.0)
    unit_id = fields.Many2one(
        'uom.uom', string='Unit of Measure',
        default=lambda self: self.env.ref('uom.uom_square_meter', raise_if_not_found=False),
        domain=lambda self: [
            ('category_id', '=', self.env.ref('uom.uom_categ_surface').id)
        ],
        ondelete='set null',
    )
    # unit_price = cost per unit = cost_total / quantity
    unit_price = fields.Float(
        string='Unit Price', compute='_compute_unit_cost', store=True, digits=(16, 2),
    )
    # total = cost_total  (pure cost, no margin)
    total = fields.Float(
        string='Total', compute='_compute_unit_cost', store=True, digits=(16, 2),
    )

    # ── Costing lines ──────────────────────────────────────────────────────────
    material_ids = fields.One2many(
        'farm.boq.line.template.material', 'template_id', string='Materials',
    )
    labor_ids = fields.One2many(
        'farm.boq.line.template.labor', 'template_id', string='Labour',
    )
    subcontractor_ids = fields.One2many(
        'farm.boq.line.template.subcontractor', 'template_id', string='Subcontractor',
    )
    equipment_ids = fields.One2many(
        'farm.boq.line.template.equipment', 'template_id', string='Equipment',
    )
    tools_ids = fields.One2many(
        'farm.boq.line.template.tools', 'template_id', string='Tools',
    )
    overhead_ids = fields.One2many(
        'farm.boq.line.template.overhead', 'template_id', string='Others',
    )

    # ── Cost totals ────────────────────────────────────────────────────────────
    material_total = fields.Float(
        string='Materials Total', compute='_compute_cost_totals', store=True, digits=(16, 2),
    )
    labor_total = fields.Float(
        string='Labour Total', compute='_compute_cost_totals', store=True, digits=(16, 2),
    )
    subcontractor_total = fields.Float(
        string='Subcontractor Total', compute='_compute_cost_totals', store=True, digits=(16, 2),
    )
    equipment_total = fields.Float(
        string='Equipment Total', compute='_compute_cost_totals', store=True, digits=(16, 2),
    )
    tools_total = fields.Float(
        string='Tools Total', compute='_compute_cost_totals', store=True, digits=(16, 2),
    )
    overhead_total = fields.Float(
        string='Others Total', compute='_compute_cost_totals', store=True, digits=(16, 2),
    )
    cost_total = fields.Float(
        string='Cost Total', compute='_compute_cost_totals', store=True, digits=(16, 2),
    )

    # ── Profitability ──────────────────────────────────────────────────────────
    # margin_percent is entered manually by the user.
    margin_percent = fields.Float(
        string='Margin (%)', default=0.0, digits=(16, 2),
    )
    selling_total = fields.Float(
        string='Selling Total', compute='_compute_profitability', store=True, digits=(16, 2),
    )
    profit = fields.Float(
        string='Profit', compute='_compute_profitability', store=True, digits=(16, 2),
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed fields
    # ────────────────────────────────────────────────────────────────────────

    @api.depends(
        'material_ids.total',
        'labor_ids.total',
        'subcontractor_ids.total',
        'equipment_ids.total',
        'tools_ids.total',
        'overhead_ids.total',
    )
    def _compute_cost_totals(self):
        for rec in self:
            rec.material_total     = sum(rec.material_ids.mapped('total'))
            rec.labor_total        = sum(rec.labor_ids.mapped('total'))
            rec.subcontractor_total = sum(rec.subcontractor_ids.mapped('total'))
            rec.equipment_total    = sum(rec.equipment_ids.mapped('total'))
            rec.tools_total        = sum(rec.tools_ids.mapped('total'))
            rec.overhead_total     = sum(rec.overhead_ids.mapped('total'))
            rec.cost_total = (
                rec.material_total
                + rec.labor_total
                + rec.subcontractor_total
                + rec.equipment_total
                + rec.tools_total
                + rec.overhead_total
            )

    @api.depends('cost_total', 'quantity')
    def _compute_unit_cost(self):
        """Cost-side fields — no margin involved.

        unit_price = cost_total / quantity   (0 when quantity = 0)
        total      = cost_total
        """
        for rec in self:
            cost = rec.cost_total or 0.0
            qty = rec.quantity or 0.0
            rec.unit_price = cost / qty if qty else 0.0
            rec.total = cost

    @api.depends('cost_total', 'margin_percent')
    def _compute_profitability(self):
        """Profitability side — driven by margin entered by the user.

        selling_total = cost_total × (1 + margin_percent / 100)
        profit        = selling_total − cost_total
        """
        for rec in self:
            cost = rec.cost_total or 0.0
            margin = rec.margin_percent or 0.0
            selling = cost * (1.0 + margin / 100.0)
            rec.selling_total = selling
            rec.profit = selling - cost

    @api.onchange('division_id')
    def _onchange_division_id(self):
        self.subdivision_id = False

    # ────────────────────────────────────────────────────────────────────────
    # Constraints
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('name', 'division_id', 'subdivision_id')
    def _check_unique_name(self):
        """Template names must be unique within the same Division + Subdivision.

        This prevents duplicate entries and ambiguous template selection from
        the Add Subitem wizard.
        """
        for rec in self:
            duplicate = self.search([
                ('name', '=', rec.name),
                ('division_id', '=', rec.division_id.id or False),
                ('subdivision_id', '=', rec.subdivision_id.id or False),
                ('id', '!=', rec.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    'A template named "%s" already exists under the same '
                    'Division / Subdivision. Template names must be unique '
                    'within their classification scope.',
                    rec.name,
                ))

    # ────────────────────────────────────────────────────────────────────────
    # Actions
    # ────────────────────────────────────────────────────────────────────────

    def action_create_boq_line(self):
        """Open wizard to select a target BOQ and instantiate this template as a BOQ Line."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create BOQ Line'),
            'res_model': 'farm.boq.line.template.use.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_template_id': self.id,
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# Shared mixin fields for service-type resource lines
# ─────────────────────────────────────────────────────────────────────────────

def _service_product_onchange(rec):
    """Auto-fill description, UoM, and unit price when a product is selected."""
    if rec.product_id:
        if not rec.description:
            rec.description = rec.product_id.name
        rec.uom_id = rec.product_id.uom_id
        rec.unit_price = rec.product_id.standard_price
    else:
        rec.uom_id = False


# ─────────────────────────────────────────────────────────────────────────────
# Materials  (Storable / Consumable / Service — all product types allowed)
# ─────────────────────────────────────────────────────────────────────────────

class FarmBoqLineTemplateMaterial(models.Model):
    _name = 'farm.boq.line.template.material'
    _description = 'BOQ Template Material'
    _order = 'id'

    template_id = fields.Many2one(
        'farm.boq.line.template', required=True, ondelete='cascade', index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='template_id.currency_id', store=False,
    )
    # All product types allowed for Materials (Storable / Consumable / Service)
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain=[('type', 'in', ['product', 'consu', 'service'])],
        ondelete='set null',
    )
    product_type = fields.Selection(
        related='product_id.type',
        string='Product Type',
        store=False,
        readonly=True,
    )
    description = fields.Char(string='Description')
    uom_id = fields.Many2one(
        'uom.uom', string='Unit',
        ondelete='restrict',
    )
    quantity = fields.Float(string='Quantity', default=1.0)
    unit_price = fields.Float(string='Unit Price')
    total = fields.Float(string='Total', compute='_compute_total', store=True)

    @api.depends('quantity', 'unit_price')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.quantity * rec.unit_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            if not self.description:
                self.description = self.product_id.name
            self.uom_id = self.product_id.uom_id
            self.unit_price = self.product_id.standard_price
        else:
            self.uom_id = False


# ─────────────────────────────────────────────────────────────────────────────
# Labour  (Service products only)
# ─────────────────────────────────────────────────────────────────────────────

class FarmBoqLineTemplateLabor(models.Model):
    _name = 'farm.boq.line.template.labor'
    _description = 'BOQ Template Labour'
    _order = 'id'

    template_id = fields.Many2one(
        'farm.boq.line.template', required=True, ondelete='cascade', index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='template_id.currency_id', store=False,
    )
    # Service products only for Labour
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain=[('type', '=', 'service')],
        ondelete='set null',
    )
    description = fields.Char(string='Description', required=True)
    uom_id = fields.Many2one(
        'uom.uom', string='Unit',
        ondelete='restrict',
    )
    # Backward-compatible field names: hours = quantity, cost_per_hour = unit_price
    hours = fields.Float(string='Qty / Hours', default=1.0)
    cost_per_hour = fields.Float(string='Unit Cost')
    total = fields.Float(string='Total', compute='_compute_total', store=True)

    @api.depends('hours', 'cost_per_hour')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.hours * rec.cost_per_hour

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            if not self.description:
                self.description = self.product_id.name
            self.uom_id = self.product_id.uom_id
            self.cost_per_hour = self.product_id.standard_price
        else:
            self.uom_id = False


# ─────────────────────────────────────────────────────────────────────────────
# Subcontractor  (Service products only)
# ─────────────────────────────────────────────────────────────────────────────

class FarmBoqLineTemplateSubcontractor(models.Model):
    _name = 'farm.boq.line.template.subcontractor'
    _description = 'BOQ Template Subcontractor'
    _order = 'id'

    template_id = fields.Many2one(
        'farm.boq.line.template', required=True, ondelete='cascade', index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='template_id.currency_id', store=False,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain=[('type', '=', 'service')],
        ondelete='set null',
    )
    description = fields.Char(string='Description')
    uom_id = fields.Many2one(
        'uom.uom', string='Unit',
        ondelete='restrict',
    )
    quantity = fields.Float(string='Quantity', default=1.0)
    unit_price = fields.Float(string='Unit Price')
    total = fields.Float(string='Total', compute='_compute_total', store=True)

    @api.depends('quantity', 'unit_price')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.quantity * rec.unit_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        _service_product_onchange(self)


# ─────────────────────────────────────────────────────────────────────────────
# Equipment  (Service products only)
# ─────────────────────────────────────────────────────────────────────────────

class FarmBoqLineTemplateEquipment(models.Model):
    _name = 'farm.boq.line.template.equipment'
    _description = 'BOQ Template Equipment'
    _order = 'id'

    template_id = fields.Many2one(
        'farm.boq.line.template', required=True, ondelete='cascade', index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='template_id.currency_id', store=False,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain=[('type', '=', 'service')],
        ondelete='set null',
    )
    description = fields.Char(string='Description')
    uom_id = fields.Many2one(
        'uom.uom', string='Unit',
        ondelete='restrict',
    )
    quantity = fields.Float(string='Quantity', default=1.0)
    unit_price = fields.Float(string='Unit Price')
    total = fields.Float(string='Total', compute='_compute_total', store=True)

    @api.depends('quantity', 'unit_price')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.quantity * rec.unit_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        _service_product_onchange(self)


# ─────────────────────────────────────────────────────────────────────────────
# Tools  (Service products only)
# ─────────────────────────────────────────────────────────────────────────────

class FarmBoqLineTemplateTools(models.Model):
    _name = 'farm.boq.line.template.tools'
    _description = 'BOQ Template Tools'
    _order = 'id'

    template_id = fields.Many2one(
        'farm.boq.line.template', required=True, ondelete='cascade', index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='template_id.currency_id', store=False,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain=[('type', '=', 'service')],
        ondelete='set null',
    )
    description = fields.Char(string='Description')
    uom_id = fields.Many2one(
        'uom.uom', string='Unit',
        ondelete='restrict',
    )
    quantity = fields.Float(string='Quantity', default=1.0)
    unit_price = fields.Float(string='Unit Price')
    total = fields.Float(string='Total', compute='_compute_total', store=True)

    @api.depends('quantity', 'unit_price')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.quantity * rec.unit_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        _service_product_onchange(self)


# ─────────────────────────────────────────────────────────────────────────────
# Others  (was: Overhead — backward-compatible; Service products only)
#
# Backward-compatibility note:
#   The model _name, DB table, and the `amount` field are preserved so that
#   existing overhead records are not lost.  The view tab is now labelled
#   "Others" and a product_id (service domain) has been added as an optional
#   field.  `total` is now computed as quantity × unit_price when a product
#   is selected; for legacy rows where only `amount` was set the
#   `unit_price` defaults to `amount` and `quantity` defaults to 1.
# ─────────────────────────────────────────────────────────────────────────────

class FarmBoqLineTemplateOverhead(models.Model):
    _name = 'farm.boq.line.template.overhead'
    _description = 'BOQ Template Others (Overhead)'
    _order = 'id'

    template_id = fields.Many2one(
        'farm.boq.line.template', required=True, ondelete='cascade', index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='template_id.currency_id', store=False,
    )
    # Service products only for Others/Overhead (optional — existing rows safe)
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain=[('type', '=', 'service')],
        ondelete='set null',
    )
    name = fields.Char(string='Description', required=True)
    uom_id = fields.Many2one(
        'uom.uom', string='Unit',
        ondelete='restrict',
    )
    quantity = fields.Float(string='Quantity', default=1.0)
    unit_price = fields.Float(string='Unit Price')
    # `amount` kept for backward compat — equals total
    amount = fields.Float(
        string='Amount',
        compute='_compute_amount', store=True, digits=(16, 2),
    )
    total = fields.Float(
        string='Total', compute='_compute_amount', store=True, digits=(16, 2),
    )

    @api.depends('quantity', 'unit_price')
    def _compute_amount(self):
        for rec in self:
            rec.total = rec.quantity * rec.unit_price
            rec.amount = rec.total  # keep backward compat

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            if not self.name:
                self.name = self.product_id.name
            self.uom_id = self.product_id.uom_id
            self.unit_price = self.product_id.standard_price
        else:
            self.uom_id = False
