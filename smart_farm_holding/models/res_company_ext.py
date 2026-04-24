from odoo import fields, models


BUSINESS_ACTIVITY_SELECTION = [
    ('construction',  'Construction'),
    ('agriculture',   'Agriculture'),
    ('manufacturing', 'Manufacturing'),
    ('livestock',     'Livestock'),
]


class ResCompanyActivityExt(models.Model):
    """
    Extends res.company with business_activity — the single source of truth
    for each company's operational domain.

    All child records (farm.project, farm.job.order, agriculture.season, etc.)
    derive their business_activity from their company, making it impossible
    for users to accidentally mix activities within the same company.
    """

    _inherit = 'res.company'

    business_activity = fields.Selection(
        selection=BUSINESS_ACTIVITY_SELECTION,
        string='Business Activity',
        index=True,
        help=(
            'The primary business activity for this company.\n\n'
            '• Construction — civil/MEP BOQ-driven projects, procurement, execution\n'
            '• Agriculture  — crop lifecycle: seasons, planning, harvest, packing\n'
            '• Manufacturing — production: plans, work orders, QC, dispatch\n'
            '• Livestock    — herd management: breeding, raising, fattening, sales\n\n'
            'Leave empty for the master Holding Company — it sees all activities.\n\n'
            'When set, all projects and records created under this company will '
            'automatically inherit this activity. Users cannot override it manually.'
        ),
    )
