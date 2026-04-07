# -*- coding: utf-8 -*-
from odoo import models, fields
from .farm_cost_type import COSTING_SECTION_SELECTION


class FarmBoqWorkType(models.Model):
    """Work-type classification inside BOQ Item Templates.
    Each work type belongs to a costing section so that when the user
    selects a section only the relevant work types are offered.

    Example:
        costing_section = 'civil'  →  Earthwork, Compaction Works, …
        costing_section = 'arch'   →  Masonry Works, Plaster Works, …
    """
    _name = 'farm.boq.work.type'
    _description = 'BOQ Work Type'
    _order = 'costing_section, sequence, name'
    _rec_name = 'name'

    name = fields.Char(string='Work Type', required=True, translate=True)
    code = fields.Char(string='Code')
    costing_section = fields.Selection(
        COSTING_SECTION_SELECTION,
        string='Costing Section',
        required=True,
        default='civil',
    )
    description = fields.Text(string='Description', translate=True)
    active = fields.Boolean(string='Active', default=True)
    sequence = fields.Integer(string='Sequence', default=10)
