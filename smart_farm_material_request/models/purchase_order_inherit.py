from odoo import api, fields, models, _


class PurchaseOrderMR(models.Model):
    """Add material_request_id link to purchase.order."""

    _inherit = 'purchase.order'

    material_request_id = fields.Many2one(
        'farm.material.request',
        string='Material Request',
        ondelete='set null',
        index=True,
        copy=False,
        help='Material Request that generated this Purchase Order.',
    )

    def button_confirm(self):
        """On PO confirmation, sync MR state to ordered."""
        result = super().button_confirm()
        self._sync_mr_state()
        return result

    def _sync_mr_state(self):
        """Push state change to linked Material Requests."""
        mrs = self.mapped('material_request_id').filtered(bool)
        if mrs:
            mrs._sync_state_from_po()


class PurchaseOrderLineMR(models.Model):
    """Add mr_line_id link to purchase.order.line."""

    _inherit = 'purchase.order.line'

    mr_line_id = fields.Many2one(
        'farm.material.request.line',
        string='MR Line',
        ondelete='set null',
        index=True,
        copy=False,
    )

    def _update_mr_received_qty(self):
        """Sync received_qty back to the linked MR line.

        Called from stock picking done / purchase receipt.
        received_qty = sum of done moves for this PO line.
        """
        if not self.mr_line_id:
            return
        received = sum(
            self.move_ids.filtered(
                lambda m: m.state == 'done'
            ).mapped('quantity')
        )
        self.mr_line_id.received_qty = received

        # Check if the whole MR is now fully received
        mr = self.mr_line_id.request_id
        if mr and mr.state == 'ordered':
            all_received = all(
                l.received_qty >= l.requested_qty
                for l in mr.line_ids
                if l.requested_qty > 0
            )
            if all_received:
                mr.state = 'received'
                mr.message_post(body=_('All materials received. MR marked as Received.'))
