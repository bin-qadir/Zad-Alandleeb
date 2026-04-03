# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FarmExpense(models.Model):
    _name = 'farm.expense'
    _description = 'Farm Expense'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'expense_date desc'

    name = fields.Char(string='Description', required=True, tracking=True)
    reference = fields.Char(string='Reference', copy=False, readonly=True, default=lambda self: _('New'))

    farm_id = fields.Many2one('farm.farm', string='Farm', required=True, tracking=True)
    field_id = fields.Many2one('farm.field', string='Field', domain="[('farm_id', '=', farm_id)]")
    crop_id = fields.Many2one('farm.crop', string='Crop', domain="[('farm_id', '=', farm_id)]")
    company_id = fields.Many2one(related='farm_id.company_id', store=True)

    expense_date = fields.Date(string='Date', required=True, tracking=True, default=fields.Date.today)

    expense_type = fields.Selection([
        ('seed', 'Seeds & Planting Material'),
        ('fertilizer', 'Fertilizers & Amendments'),
        ('pesticide', 'Pesticides & Herbicides'),
        ('labour', 'Labour'),
        ('machinery', 'Machinery & Equipment'),
        ('irrigation', 'Irrigation'),
        ('fuel', 'Fuel & Energy'),
        ('veterinary', 'Veterinary'),
        ('feed', 'Animal Feed'),
        ('infrastructure', 'Infrastructure'),
        ('other', 'Other'),
    ], string='Expense Type', required=True, tracking=True)

    amount = fields.Monetary(string='Amount', required=True, currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # Links to other modules
    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order')
    vendor_bill_id = fields.Many2one('account.move', string='Vendor Bill',
                                     domain=[('move_type', '=', 'in_invoice')])
    analytic_account_id = fields.Many2one(
        related='farm_id.analytic_account_id',
        store=True,
        string='Analytic Account',
    )
    responsible_id = fields.Many2one('res.users', string='Responsible')
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code('farm.expense') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        self.state = 'confirmed'

    def action_mark_paid(self):
        self.state = 'paid'

    def action_cancel(self):
        self.state = 'cancelled'

    def action_reset_draft(self):
        self.state = 'draft'

    def action_create_purchase_order(self):
        """Create purchase order from expense."""
        po = self.env['purchase.order'].create({
            'partner_id': self.env.company.partner_id.id,
            'origin': self.reference,
            'order_line': [(0, 0, {
                'name': self.name,
                'product_qty': 1,
                'price_unit': self.amount,
                'date_planned': self.expense_date,
            })],
        })
        self.purchase_order_id = po.id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Order'),
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
        }
