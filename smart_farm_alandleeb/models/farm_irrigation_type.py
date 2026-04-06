# -*- coding: utf-8 -*-
from odoo import models, fields


class FarmIrrigationType(models.Model):
    _name = 'farm.irrigation.type'
    _description = 'Irrigation Type'
    _order = 'name'

    name = fields.Char(string='Irrigation Type', required=True, translate=True)
    description = fields.Text(string='Description', translate=True)
