# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class FarmFarm(models.Model):
    _name = 'farm.farm'
    _description = 'Farm'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'

    name = fields.Char(
        string='Farm Name',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='Farm Code',
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ], string='Status', default='draft', tracking=True)

    manager_id = fields.Many2one(
        'res.users',
        string='Farm Manager',
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Contact',
    )

    # Location
    street = fields.Char(string='Street')
    city = fields.Char(string='City')
    state_id = fields.Many2one('res.country.state', string='State')
    country_id = fields.Many2one('res.country', string='Country')
    zip = fields.Char(string='ZIP')
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))

    # Dimensions  (unit: m²)
    total_area = fields.Float(
        string='Total Area (m²)',
        digits=(16, 2),
        compute='_compute_total_area',
        store=True,
        help='Total area in square meters — auto-calculated from all registered fields.',
    )
    total_area_ha = fields.Float(
        string='Total Area (Ha)',
        digits=(10, 4),
        compute='_compute_total_area',
        store=True,
        help='Total area converted to hectares (1 Ha = 10,000 m²).',
    )

    # Relations
    field_ids = fields.One2many('farm.field', 'farm_id', string='Fields')
    field_count = fields.Integer(string='Field Count', compute='_compute_field_count')
    project_id = fields.Many2one(
        'project.project',
        string='Related Project',
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
    )

    notes = fields.Html(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', _('New')) == _('New'):
                vals['code'] = self.env['ir.sequence'].next_by_code('farm.farm') or _('New')
        return super().create(vals_list)

    @api.depends('field_ids', 'field_ids.area')
    def _compute_total_area(self):
        for rec in self:
            rec.total_area = sum(rec.field_ids.mapped('area'))
            rec.total_area_ha = rec.total_area / 10000.0 if rec.total_area else 0.0

    @api.depends('field_ids')
    def _compute_field_count(self):
        for rec in self:
            rec.field_count = len(rec.field_ids)

    def action_activate(self):
        self.state = 'active'

    def action_deactivate(self):
        self.state = 'inactive'

    def action_view_fields(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fields'),
            'res_model': 'farm.field',
            'view_mode': 'list,form',
            'domain': [('farm_id', '=', self.id)],
            'context': {'default_farm_id': self.id},
        }

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, f'[{rec.code}] {rec.name}'))
        return result
