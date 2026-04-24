"""
Construction Project — Buildings, Floors, Zones
=================================================

Three lightweight models that define the physical composition of a
construction project at the Project Definition stage (before BOQ).

  construction.project.building
    └── construction.project.building.floor

  construction.project.zone
"""
from odoo import api, fields, models


# ─────────────────────────────────────────────────────────────────────────────
# Building
# ─────────────────────────────────────────────────────────────────────────────

class ConstructionProjectBuilding(models.Model):
    _name        = 'construction.project.building'
    _description = 'Construction Project — Building'
    _order       = 'sequence, name'

    project_id = fields.Many2one(
        comodel_name='farm.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string='Building Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)

    floor_ids = fields.One2many(
        comodel_name='construction.project.building.floor',
        inverse_name='building_id',
        string='Floors',
    )

    # ── Computed ──────────────────────────────────────────────────────────────

    floor_count = fields.Integer(
        string='Floors',
        compute='_compute_floor_stats',
    )
    total_floor_area = fields.Float(
        string='Total Floor Area (m²)',
        digits=(16, 2),
        compute='_compute_floor_stats',
    )

    @api.depends('floor_ids', 'floor_ids.area')
    def _compute_floor_stats(self):
        for rec in self:
            rec.floor_count      = len(rec.floor_ids)
            rec.total_floor_area = sum(rec.floor_ids.mapped('area'))


# ─────────────────────────────────────────────────────────────────────────────
# Building Floor
# ─────────────────────────────────────────────────────────────────────────────

class ConstructionProjectBuildingFloor(models.Model):
    _name        = 'construction.project.building.floor'
    _description = 'Construction Project — Building Floor'
    _order       = 'building_id, floor_no, name'

    building_id = fields.Many2one(
        comodel_name='construction.project.building',
        string='Building',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(
        string='Floor Name',
        required=True,
        help='e.g. Ground Floor, First Floor, Basement, Roof',
    )
    floor_no = fields.Integer(
        string='Floor No.',
        default=0,
        help='Numeric level: -1 = Basement, 0 = Ground, 1 = First, …',
    )
    area = fields.Float(
        string='Area (m²)',
        digits=(16, 2),
    )

    # Convenience: store project_id for domain filters / reports
    project_id = fields.Many2one(
        comodel_name='farm.project',
        string='Project',
        related='building_id.project_id',
        store=True,
        index=True,
        readonly=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Zone
# ─────────────────────────────────────────────────────────────────────────────

ZONE_TYPE_SELECTION = [
    ('residential', 'Residential'),
    ('commercial',  'Commercial'),
    ('industrial',  'Industrial'),
    ('amenity',     'Amenity / Open Space'),
    ('parking',     'Parking'),
    ('utility',     'Utility / Services'),
    ('other',       'Other'),
]


class ConstructionProjectZone(models.Model):
    _name        = 'construction.project.zone'
    _description = 'Construction Project — Zone'
    _order       = 'name'

    project_id = fields.Many2one(
        comodel_name='farm.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string='Zone Name', required=True)
    zone_type = fields.Selection(
        selection=ZONE_TYPE_SELECTION,
        string='Zone Type',
    )
    area = fields.Float(
        string='Area (m²)',
        digits=(16, 2),
    )
