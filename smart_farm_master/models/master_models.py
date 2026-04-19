from odoo import fields, models


class FarmCropType(models.Model):
    _name = 'farm.crop.type'
    _description = 'Farm Crop Type'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(string='Active', default=True)


class FarmCostType(models.Model):
    _name = 'farm.cost.type'
    _description = 'Farm Cost Type'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(string='Active', default=True)


class FarmWorkType(models.Model):
    _name = 'farm.work.type'
    _description = 'Farm Work Type'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(string='Active', default=True)


class FarmSensorType(models.Model):
    _name = 'farm.sensor.type'
    _description = 'Farm Sensor Type'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(string='Active', default=True)
