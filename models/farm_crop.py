# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date


class FarmCropType(models.Model):
    _name = 'farm.crop.type'
    _description = 'Crop Type'
    _order = 'name'

    name = fields.Char(string='Crop Type', required=True)
    category = fields.Selection([
        ('grain', 'Grain & Cereals'),
        ('vegetable', 'Vegetables'),
        ('fruit', 'Fruits'),
        ('legume', 'Legumes'),
        ('herb', 'Herbs & Spices'),
        ('fodder', 'Fodder / Feed Crops'),
        ('other', 'Other'),
    ], string='Category', required=True)
    average_duration = fields.Integer(string='Avg. Growing Days')
    product_id = fields.Many2one('product.product', string='Related Product')
    notes = fields.Text(string='Notes')
    active = fields.Boolean(default=True)


class FarmCrop(models.Model):
    _name = 'farm.crop'
    _description = 'Crop Planting'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'planting_date desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))

    field_id = fields.Many2one('farm.field', string='Field', required=True, tracking=True)
    farm_id = fields.Many2one(related='field_id.farm_id', store=True, string='Farm')
    company_id = fields.Many2one(related='farm_id.company_id', store=True)

    crop_type_id = fields.Many2one('farm.crop.type', string='Crop Type', required=True, tracking=True)
    variety = fields.Char(string='Variety / Cultivar')

    planting_date = fields.Date(string='Planting Date', required=True, tracking=True)
    expected_harvest_date = fields.Date(string='Expected Harvest Date', tracking=True)
    actual_harvest_date = fields.Date(string='Actual Harvest Date', tracking=True)

    area_planted = fields.Float(string='Area Planted (Ha)', digits=(10, 3))
    expected_yield = fields.Float(string='Expected Yield (Kg)', digits=(10, 2))
    actual_yield = fields.Float(string='Actual Yield (Kg)', digits=(10, 2), compute='_compute_actual_yield', store=True)

    state = fields.Selection([
        ('planning', 'Planning'),
        ('planted', 'Planted'),
        ('growing', 'Growing'),
        ('harvested', 'Harvested'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='planning', tracking=True)

    project_task_id = fields.Many2one('project.task', string='Project Task')
    harvest_ids = fields.One2many('farm.harvest', 'crop_id', string='Harvest Records')
    harvest_count = fields.Integer(compute='_compute_harvest_count', string='Harvests')

    responsible_id = fields.Many2one('res.users', string='Responsible', tracking=True)
    notes = fields.Html(string='Notes')

    # Seeds / inputs
    seed_product_id = fields.Many2one('product.product', string='Seed / Seedling Product')
    seed_qty = fields.Float(string='Seed Qty Used', digits=(10, 3))
    seed_uom_id = fields.Many2one('uom.uom', string='UoM')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('farm.crop') or _('New')
        return super().create(vals_list)

    @api.depends('harvest_ids.quantity_harvested')
    def _compute_actual_yield(self):
        for rec in self:
            rec.actual_yield = sum(rec.harvest_ids.mapped('quantity_harvested'))

    @api.depends('harvest_ids')
    def _compute_harvest_count(self):
        for rec in self:
            rec.harvest_count = len(rec.harvest_ids)

    @api.constrains('planting_date', 'expected_harvest_date')
    def _check_dates(self):
        for rec in self:
            if rec.planting_date and rec.expected_harvest_date:
                if rec.expected_harvest_date < rec.planting_date:
                    raise ValidationError(_('Expected harvest date cannot be before planting date.'))

    def action_plant(self):
        self.write({'state': 'planted'})
        self.field_id.write({'state': 'planted', 'current_crop_id': self.id})

    def action_start_growing(self):
        self.state = 'growing'

    def action_harvest(self):
        self.state = 'harvested'
        self.actual_harvest_date = date.today()
        self.field_id.write({'state': 'harvested', 'current_crop_id': False})

    def action_fail(self):
        self.state = 'failed'
        self.field_id.write({'state': 'fallow', 'current_crop_id': False})

    def action_cancel(self):
        self.state = 'cancelled'

    def action_view_harvests(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Harvest Records'),
            'res_model': 'farm.harvest',
            'view_mode': 'list,form',
            'domain': [('crop_id', '=', self.id)],
            'context': {'default_crop_id': self.id},
        }
