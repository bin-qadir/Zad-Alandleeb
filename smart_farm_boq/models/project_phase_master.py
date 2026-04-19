from odoo import fields, models


class ProjectPhaseMaster(models.Model):
    """Project Phase Master — planning classification (Pre-Tender / Tender / Post-Tender).

    This is intentionally separate from the BOQ workflow status (draft → approved).
    Phases represent when in the project lifecycle a piece of work belongs,
    not the document review/approval state.
    """

    _name = 'project.phase.master'
    _description = 'Project Phase'
    _order = 'sequence, id'

    name = fields.Char(string='Phase Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
