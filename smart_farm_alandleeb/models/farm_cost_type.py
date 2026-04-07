# -*- coding: utf-8 -*-
from odoo import models, fields

# Shared across models — import from here to keep DRY
COSTING_SECTION_SELECTION = [
    ('civil', 'Civil'),
    ('arch', 'Architecture'),
    ('mechanical', 'Mechanical'),
    ('electrical', 'Electrical'),
    ('irrigation', 'Irrigation'),
    ('control_system', 'Control System'),
    ('other', 'Other'),
]

SECTION_COSTING_STATES = [
    ('draft', 'Draft'),
    ('price_study', 'Price Study'),
    ('quantity_review', 'Quantity Review'),
    ('estimated_costing', 'Estimated Costing'),
    ('cost_analysis', 'Cost Analysis'),
    ('approved', 'Approved'),
]


class FarmCostType(models.Model):
    _name = 'farm.cost.type'
    _description = 'Farm Cost Type'
    _order = 'costing_section, category, name'

    name = fields.Char(string='Cost Type', required=True, translate=True)
    costing_section = fields.Selection(
        COSTING_SECTION_SELECTION,
        string='Works Division',
        required=True,
        default='other',
    )
    category = fields.Selection([
        ('material', 'Material'),
        ('labor', 'Labor'),
        ('overhead', 'Overhead'),
    ], string='Category', required=True, default='material')
    description = fields.Text(string='Description', translate=True)
