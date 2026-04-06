# -*- coding: utf-8 -*-
from odoo import models, fields, api
from .farm_cost_type import COSTING_SECTION_SELECTION


class FarmCostLine(models.Model):
    _name = 'farm.cost.line'
    _description = 'Farm Cost Line'
    _order = 'field_id, costing_section, sequence, id'

    field_id = fields.Many2one(
        'farm.field', string='Field', required=True, ondelete='cascade',
    )
    sequence = fields.Integer(string='Sequence', default=10)

    # Section / note support (standard Odoo pattern)
    display_type = fields.Selection([
        ('line_section', 'Section'),
        ('line_note', 'Note'),
    ], default=False, string='Display Type')

    # Section this line belongs to
    costing_section = fields.Selection(
        COSTING_SECTION_SELECTION,
        string='Costing Section',
        required=True,
        default='other',
    )

    name = fields.Char(string='Description')
    cost_type_id = fields.Many2one(
        'farm.cost.type', string='Cost Type', ondelete='restrict',
    )
    product_id = fields.Many2one(
        'product.product', string='Product', ondelete='restrict',
    )
    quantity = fields.Float(string='Quantity', digits=(16, 3), default=1.0)
    unit_cost = fields.Float(string='Unit Cost', digits=(16, 2))
    total_cost = fields.Float(
        string='Total Cost', digits=(16, 2),
        compute='_compute_total_cost', store=True,
    )

    @api.depends('quantity', 'unit_cost', 'display_type')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = 0.0 if rec.display_type else rec.quantity * rec.unit_cost

    # ── Category mirror — for display in analysis wizard lists ───────────────
    cost_category = fields.Selection(
        related='cost_type_id.category',
        string='Category',
        store=False,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # Ensure costing_section is populated from context when not yet set
        if 'costing_section' in fields_list and not res.get('costing_section'):
            section = self.env.context.get('default_costing_section')
            if section:
                res['costing_section'] = section
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Safety net: stamp costing_section from context if not set in vals."""
        section = self.env.context.get('default_costing_section', 'other')
        for vals in vals_list:
            if not vals.get('costing_section'):
                vals['costing_section'] = section
        return super().create(vals_list)

    @api.onchange('cost_type_id')
    def _onchange_cost_type_id(self):
        """Auto-fill costing_section from selected cost type."""
        if self.cost_type_id and self.cost_type_id.costing_section:
            self.costing_section = self.cost_type_id.costing_section
