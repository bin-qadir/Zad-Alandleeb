"""
farm.boq — Construction Project Definition link
=================================================

Adds two OPTIONAL fields to farm.boq:
  • building_id — links a BOQ to a construction.project.building
  • zone_id     — links a BOQ to a construction.project.zone

No constraints.  No required fields.  No deletions.
The existing BOQ engine, costing, templates, and quantities are untouched.
"""
from odoo import fields, models


class FarmBoqConstructionExt(models.Model):
    _inherit = 'farm.boq'

    building_id = fields.Many2one(
        comodel_name='construction.project.building',
        string='Building',
        ondelete='set null',
        index=True,
        help='Optional: link this BOQ to a specific building within the project.',
    )
    zone_id = fields.Many2one(
        comodel_name='construction.project.zone',
        string='Zone',
        ondelete='set null',
        index=True,
        help='Optional: link this BOQ to a specific zone within the project.',
    )
