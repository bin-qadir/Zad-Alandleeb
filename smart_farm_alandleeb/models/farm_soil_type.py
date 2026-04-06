# -*- coding: utf-8 -*-
from odoo import models, fields


class FarmSoilType(models.Model):
    _name = 'farm.soil.type'
    _description = 'Soil Type'
    _order = 'name'

    name = fields.Char(string='Soil Type', required=True, translate=True)
    description = fields.Text(string='Description', translate=True)
