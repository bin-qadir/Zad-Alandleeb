from odoo import fields, models


class FarmJobOrderContract(models.Model):
    """Extend farm.job.order with contract linkage."""

    _inherit = 'farm.job.order'

    contract_id = fields.Many2one(
        'farm.contract',
        string='Contract',
        ondelete='restrict',
        index=True,
        tracking=True,
        domain="[('project_id', '=', project_id), ('state', 'in', ['approved', 'active'])]",
        help='Contract under which this Job Order is executed.',
    )
