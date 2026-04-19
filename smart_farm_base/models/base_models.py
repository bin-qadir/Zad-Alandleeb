from odoo import fields, models


class SmartFarmTag(models.Model):
    _name = 'smart.farm.tag'
    _description = 'Smart Farm Tag'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(string='Active', default=True)


class SmartFarmStage(models.Model):
    _name = 'smart.farm.stage'
    _description = 'Smart Farm Stage'
    _order = 'sequence, name'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
