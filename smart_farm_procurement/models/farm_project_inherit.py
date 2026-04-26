from odoo import fields, models, _


class FarmProjectProcurementExt(models.Model):
    """Extend farm.project with Vendor Bills navigation.

    Vendor bills are derived from Purchase Orders linked to this project
    (via purchase.order.farm_project_id, defined in this module).
    No additional model dependency is needed.
    """

    _inherit = 'farm.project'

    # ── Vendor Bill count ─────────────────────────────────────────────────────

    vendor_bill_count = fields.Integer(
        string='Vendor Bills',
        compute='_compute_vendor_bill_count',
        help='Number of vendor bills from purchase orders linked to this project.',
    )

    def _compute_vendor_bill_count(self):
        PO = self.env['purchase.order']
        for rec in self:
            if not rec.id:
                rec.vendor_bill_count = 0
                continue
            pos = PO.search([('farm_project_id', '=', rec.id)])
            bills = pos.mapped('invoice_ids').filtered(
                lambda m: m.move_type in ('in_invoice', 'in_refund')
            )
            rec.vendor_bill_count = len(bills)

    def action_open_vendor_bills(self):
        """Open Vendor Bills from Purchase Orders linked to this project."""
        self.ensure_one()
        PO = self.env['purchase.order']
        pos = PO.search([('farm_project_id', '=', self.id)])
        bill_ids = pos.mapped('invoice_ids').filtered(
            lambda m: m.move_type in ('in_invoice', 'in_refund')
        ).ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bills — %s') % self.name,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', bill_ids)],
        }
