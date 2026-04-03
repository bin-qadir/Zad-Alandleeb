# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FarmField(models.Model):
    _name = 'farm.field'
    _description = 'Farm Field / Plot'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'farm_id, name'

    name = fields.Char(string='Field Name', required=True, tracking=True)
    code = fields.Char(string='Field Code', copy=False, readonly=True, default=lambda self: _('New'))

    farm_id = fields.Many2one('farm.farm', string='Farm', required=True, ondelete='cascade', tracking=True)
    company_id = fields.Many2one(related='farm_id.company_id', store=True)

    area = fields.Float(string='Area (Ha)', digits=(10, 3))
    soil_type = fields.Selection([
        ('clay', 'Clay'),
        ('sandy', 'Sandy'),
        ('loamy', 'Loamy'),
        ('silty', 'Silty'),
        ('peaty', 'Peaty'),
        ('chalky', 'Chalky'),
    ], string='Soil Type')

    irrigation_type = fields.Selection([
        ('drip', 'Drip Irrigation'),
        ('sprinkler', 'Sprinkler'),
        ('flood', 'Flood'),
        ('manual', 'Manual'),
        ('none', 'None'),
    ], string='Irrigation Type')

    state = fields.Selection([
        ('available', 'Available'),
        ('planted', 'Planted'),
        ('harvested', 'Harvested'),
        ('fallow', 'Fallow'),
        ('maintenance', 'Maintenance'),
    ], string='Status', default='available', tracking=True)

    current_crop_id = fields.Many2one('farm.crop', string='Current Crop', readonly=True)
    crop_ids = fields.One2many('farm.crop', 'field_id', string='Crop History')
    crop_count = fields.Integer(compute='_compute_crop_count', string='Crops')

    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))
    notes = fields.Html(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', _('New')) == _('New'):
                vals['code'] = self.env['ir.sequence'].next_by_code('farm.field') or _('New')
        return super().create(vals_list)

    @api.depends('crop_ids')
    def _compute_crop_count(self):
        for rec in self:
            rec.crop_count = len(rec.crop_ids)

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, f'{rec.farm_id.name} / {rec.name}'))
        return result
