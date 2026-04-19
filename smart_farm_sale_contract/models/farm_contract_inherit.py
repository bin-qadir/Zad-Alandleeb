from odoo import fields, models


class FarmContractSaleLink(models.Model):
    """Add a back-link from farm.contract → sale.order.

    Populated automatically by sale.order.action_create_farm_contract().
    Read-only in the contract form; navigation is via the stat button.
    """

    _inherit = 'farm.contract'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        ondelete='restrict',
        index=True,
        readonly=True,
        copy=False,
        tracking=True,
        help='Sale Order from which this contract was generated.',
    )
