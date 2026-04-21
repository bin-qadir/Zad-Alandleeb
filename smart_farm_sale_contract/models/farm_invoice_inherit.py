from odoo import fields, models


class AccountMoveSmartFarm(models.Model):
    """Extend account.move (invoices / vendor bills) with a farm project link.

    Adds farm_project_id so that:
    • Customer invoices (move_type='out_invoice') contribute to project revenue
    • Vendor bills    (move_type='in_invoice') contribute to vendor_bill_cost

    The field is optional (no required=True, ondelete='set null') so that
    existing accounting documents are unaffected.
    """

    _inherit = 'account.move'

    farm_project_id = fields.Many2one(
        comodel_name='farm.project',
        string='Farm Project',
        ondelete='set null',
        index=True,
        copy=False,
        help=(
            'Link this invoice / vendor bill to a Smart Farm project.\n\n'
            '• Customer invoices (Sales) → counted as project revenue\n'
            '• Vendor bills (Purchases)  → counted as vendor bill cost\n\n'
            'Leaving this blank has no effect on standard accounting.'
        ),
    )
