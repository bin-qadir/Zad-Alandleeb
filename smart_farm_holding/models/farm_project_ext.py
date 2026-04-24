from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


# Dynamic label map: activity → what to call this type of project
_PROJECT_LABEL = {
    'construction':  'Construction Project',
    'agriculture':   'Farm Project',
    'manufacturing': 'Production Project',
    'livestock':     'Livestock Operation',
}


class FarmProjectHoldingExt(models.Model):
    """
    Holding-level extension to farm.project.

    1. Adds company_id (multi-company isolation).
    2. Overrides business_activity to be auto-derived from the company.
       Users can no longer change it manually — it follows the company.
    3. Adds project_label: a dynamic string that changes the project title
       based on business activity.
    4. Adds AI decision layer fields.
    5. Adds a cross-activity constraint.
    """

    _inherit = 'farm.project'

    # ── Company (source of truth for activity) ────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        index=True,
        help='The operational company this project belongs to.',
    )

    # ── Business Activity — AUTO-DERIVED from company ─────────────────────────
    # Override the writable Selection in farm_project.py with a computed field.
    # This ensures the activity is always locked to the company's domain.

    business_activity = fields.Selection(
        compute='_compute_business_activity',
        store=True,
        readonly=True,
        # Keep tracking so chatter logs if company changes
        tracking=True,
    )

    @api.depends('company_id', 'company_id.business_activity')
    def _compute_business_activity(self):
        for rec in self:
            rec.business_activity = rec.company_id.business_activity or False

    # ── Dynamic Project Label ─────────────────────────────────────────────────

    project_label = fields.Char(
        string='Project Type Label',
        compute='_compute_project_label',
        store=False,
        help='Human-readable label for this project type, derived from business activity.',
    )

    @api.depends('business_activity')
    def _compute_project_label(self):
        for rec in self:
            rec.project_label = _PROJECT_LABEL.get(
                rec.business_activity, _('Project')
            )

    # ── AI Decision Layer ─────────────────────────────────────────────────────

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

    # ── Cross-Activity Constraint ─────────────────────────────────────────────

    @api.constrains('company_id', 'project_type', 'lifecycle_stage_id')
    def _check_no_cross_activity(self):
        """
        Prevent cross-activity data corruption.

        Rules:
        - project_type must match the company's business_activity.
        - lifecycle_stage_id must match the company's business_activity.
        """
        for rec in self:
            act = rec.business_activity  # auto-derived from company

            if rec.project_type and act and rec.project_type.activity != act:
                raise ValidationError(_(
                    'Project type "%(t)s" belongs to activity "%(ta)s" but '
                    'company "%(c)s" is a %(ca)s company. '
                    'Please select a project type that matches the company activity.',
                    t=rec.project_type.name,
                    ta=rec.project_type.activity,
                    c=rec.company_id.name,
                    ca=act,
                ))

            if rec.lifecycle_stage_id and act and rec.lifecycle_stage_id.business_activity != act:
                raise ValidationError(_(
                    'Lifecycle stage "%(s)s" belongs to activity "%(sa)s" but '
                    'company "%(c)s" is a %(ca)s company. '
                    'Please select a lifecycle stage that matches the company activity.',
                    s=rec.lifecycle_stage_id.name,
                    sa=rec.lifecycle_stage_id.business_activity,
                    c=rec.company_id.name,
                    ca=act,
                ))
