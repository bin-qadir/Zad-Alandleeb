from odoo import api, fields, models


class FarmBoqLineMaterial(models.Model):
    _name = 'farm.boq.line.material'
    _description = 'BOQ Line Material'
    _order = 'id'

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
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        ondelete='set null',
    )
    description = fields.Char(string='Description')
    uom_id = fields.Many2one(
        'uom.uom', string='Unit',
        domain="[('category_id', '=', product_id.uom_id.category_id)]",
        ondelete='restrict',
    )
    quantity = fields.Float(string='Quantity', default=1.0)
    unit_price = fields.Float(string='Unit Price')
    total = fields.Float(
        string='Total',
        compute='_compute_total',
        store=True,
    )

    @api.depends('quantity', 'unit_price')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.quantity * rec.unit_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.unit_price = self.product_id.standard_price
            self.uom_id = self.product_id.uom_id
        else:
            self.uom_id = False
