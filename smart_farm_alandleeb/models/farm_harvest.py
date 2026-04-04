# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FarmHarvest(models.Model):
    _name = 'farm.harvest'
    _description = 'Harvest Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'harvest_date desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))

    crop_id = fields.Many2one('farm.crop', string='Crop', required=True, tracking=True)
    field_id = fields.Many2one(related='crop_id.field_id', store=True, string='Field')
    farm_id = fields.Many2one(related='crop_id.farm_id', store=True, string='Farm')
    company_id = fields.Many2one(related='farm_id.company_id', store=True)

    harvest_date = fields.Date(string='Harvest Date', required=True, tracking=True)
    responsible_id = fields.Many2one('res.users', string='Harvested By', tracking=True)

    product_id = fields.Many2one('product.product', string='Product', required=True)
    quantity_harvested = fields.Float(string='Quantity Harvested', digits=(10, 3), required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)

    quality_grade = fields.Selection([
        ('premium', 'Premium'),
        ('grade_a', 'Grade A'),
        ('grade_b', 'Grade B'),
        ('grade_c', 'Grade C'),
        ('rejected', 'Rejected'),
    ], string='Quality Grade', default='grade_a', tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_stock', 'In Stock'),
        ('sold', 'Sold'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # Stock
    stock_picking_id = fields.Many2one('stock.picking', string='Stock Transfer', readonly=True)
    location_dest_id = fields.Many2one(
        'stock.location',
        string='Destination Location',
        domain=[('usage', '=', 'internal')],
    )
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)

    # Financials
    unit_price = fields.Monetary(string='Unit Price', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    total_value = fields.Monetary(string='Total Value', compute='_compute_total_value', store=True)

    loss_quantity = fields.Float(string='Loss / Waste (Kg)', digits=(10, 3))
    loss_reason = fields.Char(string='Loss Reason')

    notes = fields.Html(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('farm.harvest') or _('New')
        return super().create(vals_list)

    @api.depends('quantity_harvested', 'unit_price')
    def _compute_total_value(self):
        for rec in self:
            rec.total_value = rec.quantity_harvested * rec.unit_price

    def action_confirm(self):
        self.state = 'confirmed'

    def action_receive_stock(self):
        """Create a stock picking to receive harvested goods into inventory."""
        if not self.location_dest_id:
            raise UserError(_('Please set the destination location before receiving stock.'))

        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id.company_id', '=', self.company_id.id),
        ], limit=1)

        if not picking_type:
            raise UserError(_('No incoming picking type found for this company.'))

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': self.env.ref('stock.location_suppliers').id,
            'location_dest_id': self.location_dest_id.id,
            'origin': self.name,
            'move_ids': [(0, 0, {
                'name': self.product_id.name,
                'product_id': self.product_id.id,
                'product_uom_qty': self.quantity_harvested,
                'product_uom': self.uom_id.id,
                'location_id': self.env.ref('stock.location_suppliers').id,
                'location_dest_id': self.location_dest_id.id,
            })],
        })
        self.stock_picking_id = picking.id
        self.state = 'in_stock'
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock Transfer'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
        }

    def action_create_sale_order(self):
        """Create a sale order from this harvest."""
        sale_order = self.env['sale.order'].create({
            'partner_id': self.env.company.partner_id.id,
            'origin': self.name,
            'order_line': [(0, 0, {
                'product_id': self.product_id.id,
                'product_uom_qty': self.quantity_harvested,
                'product_uom': self.uom_id.id,
                'price_unit': self.unit_price,
            })],
        })
        self.sale_order_id = sale_order.id
        self.state = 'sold'
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order'),
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
        }

    def action_cancel(self):
        self.state = 'cancelled'
