from odoo import fields, models


class FarmProjectHoldingExt(models.Model):
    """
    Extension of farm.project — adds company_id and AI risk fields
    required for multi-company record rules and the holding dashboard.
    """

    _inherit = 'farm.project'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        index=True,
        help='The operational company this project belongs to.',
    )

    # ── AI Decision Layer ─────────────────────────────────────────────────────
    # Added to farm.project so the holding dashboard can aggregate risk scores

    risk_score = fields.Float(
        string='Risk Score',
        default=0.0,
        digits=(5, 1),
        help='Overall risk 0–100 for this project.',
    )
    delay_score = fields.Float(
        string='Delay Score',
        default=0.0,
        digits=(5, 1),
    )
    budget_risk = fields.Float(
        string='Budget Risk',
        default=0.0,
        digits=(5, 1),
    )
    claim_readiness = fields.Float(
        string='Claim Readiness',
        default=0.0,
        digits=(5, 1),
    )
    next_recommended_action = fields.Text(
        string='Next Recommended Action',
    )
