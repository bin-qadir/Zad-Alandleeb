# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FarmLivestockCategory(models.Model):
    _name = 'farm.livestock.category'
    _description = 'Livestock Category'

    name = fields.Char(string='Category', required=True)
    code = fields.Char(string='Code')
    active = fields.Boolean(default=True)


class FarmLivestock(models.Model):
    _name = 'farm.livestock'
    _description = 'Livestock'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'farm_id, tag_number'

    name = fields.Char(string='Name / ID', required=True, tracking=True)
    tag_number = fields.Char(string='Tag / Ear Number', tracking=True, copy=False)

    farm_id = fields.Many2one('farm.farm', string='Farm', required=True, tracking=True)
    company_id = fields.Many2one(related='farm_id.company_id', store=True)

    category_id = fields.Many2one('farm.livestock.category', string='Category', required=True)
    species = fields.Char(string='Species / Breed')

    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('unknown', 'Unknown'),
    ], string='Gender', default='unknown')

    date_of_birth = fields.Date(string='Date of Birth')
    age = fields.Integer(string='Age (months)', compute='_compute_age')
    weight = fields.Float(string='Weight (Kg)', digits=(10, 2), tracking=True)

    state = fields.Selection([
        ('active', 'Active'),
        ('sick', 'Sick'),
        ('sold', 'Sold'),
        ('deceased', 'Deceased'),
    ], string='Status', default='active', tracking=True)

    purchase_date = fields.Date(string='Acquisition Date')
    purchase_price = fields.Monetary(string='Acquisition Cost', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order')

    responsible_id = fields.Many2one('res.users', string='Responsible')
    notes = fields.Html(string='Notes')

    @api.depends('date_of_birth')
    def _compute_age(self):
        from datetime import date
        today = date.today()
        for rec in self:
            if rec.date_of_birth:
                delta = today - rec.date_of_birth
                rec.age = int(delta.days / 30)
            else:
                rec.age = 0

    def action_mark_sick(self):
        self.state = 'sick'

    def action_mark_active(self):
        self.state = 'active'

    def action_mark_sold(self):
        self.state = 'sold'

    def action_mark_deceased(self):
        self.state = 'deceased'

    def name_get(self):
        result = []
        for rec in self:
            tag = f' [{rec.tag_number}]' if rec.tag_number else ''
            result.append((rec.id, f'{rec.name}{tag}'))
        return result
