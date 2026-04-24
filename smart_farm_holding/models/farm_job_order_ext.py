from odoo import api, fields, models


class FarmJobOrderHoldingExt(models.Model):
    """
    Holding-level extension to farm.job.order.

    Overrides business_activity to be auto-derived from the parent project's
    company_id, making it impossible for users to select a mismatched activity.
    The field becomes fully computed — no manual entry permitted.
    """

    _inherit = 'farm.job.order'

    # ── Business Activity — AUTO-DERIVED from project → company ──────────────
    # Override the writable Selection in farm_job_order.py with a computed field.

    business_activity = fields.Selection(
        compute='_compute_business_activity',
        store=True,
        readonly=True,
        tracking=True,
    )

    @api.depends('project_id', 'project_id.company_id', 'project_id.company_id.business_activity')
    def _compute_business_activity(self):
        for rec in self:
            if rec.project_id and rec.project_id.company_id:
                rec.business_activity = rec.project_id.company_id.business_activity or False
            elif rec.project_id and rec.project_id.business_activity:
                # Fallback: read from project directly (handles cases where
                # project_id.company_id is not yet available in the compute chain)
                rec.business_activity = rec.project_id.business_activity
            else:
                rec.business_activity = False

    # ── Suppress the manual onchange that used to clear lifecycle stage ────────
    # The original _onchange_business_activity_clear_lifecycle is still present
    # on the base model but will no longer fire meaningfully since the field is
    # now readonly/computed. Keeping it harmless; no need to override.
