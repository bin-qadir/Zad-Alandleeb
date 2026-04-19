from odoo import fields, models


class FarmField(models.Model):
    _name = 'farm.field'
    _description = 'Farm Field'
    _order = 'project_id, name'

    name = fields.Char(string='Name', required=True)
    project_id = fields.Many2one(
        comodel_name='farm.project',
        string='Farm Project',
        required=True,
        ondelete='cascade',
    )
    crop_type_id = fields.Many2one(
        comodel_name='farm.crop.type',
        string='Crop Type',
        ondelete='set null',
    )
    area = fields.Float(string='Area (ha)')
    notes = fields.Text(string='Notes')
