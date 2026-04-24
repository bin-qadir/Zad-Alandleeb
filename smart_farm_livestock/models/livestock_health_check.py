from odoo import api, fields, models, _


class LivestockHealthCheck(models.Model):
    """Health check — veterinary examination and treatment record."""

    _name = 'livestock.health.check'
    _description = 'Livestock Health Check'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'check_date desc, name'
    _rec_name = 'name'

    name = fields.Char(string='Reference', required=True, tracking=True)

    # ── Context ───────────────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        related='herd_id.company_id',
        store=True,
        readonly=True,
    )
    herd_id = fields.Many2one(
        comodel_name='livestock.herd',
        string='Herd',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    animal_id = fields.Many2one(
        comodel_name='livestock.animal',
        string='Animal (if individual)',
        domain="[('herd_id','=',herd_id)]",
        ondelete='set null',
    )

    # ── Check Details ─────────────────────────────────────────────────────────

    check_date = fields.Date(string='Check Date', required=True, default=fields.Date.today)
    check_type = fields.Selection(
        selection=[
            ('routine',      'Routine Check'),
            ('vaccination',  'Vaccination'),
            ('treatment',    'Treatment'),
            ('deworming',    'Deworming'),
            ('emergency',    'Emergency'),
            ('pre_sale',     'Pre-Sale Inspection'),
            ('other',        'Other'),
        ],
        string='Check Type',
        required=True,
        default='routine',
    )
    veterinarian_id = fields.Many2one(
        comodel_name='res.users',
        string='Veterinarian / Inspector',
    )
    veterinarian_name = fields.Char(
        string='External Vet Name',
        help='If vet is not a system user.',
    )

    # ── Medical ───────────────────────────────────────────────────────────────

    diagnosis = fields.Text(string='Diagnosis / Findings')
    treatment = fields.Text(string='Treatment Applied')
    medication = fields.Char(string='Medication / Vaccine')
    dosage = fields.Char(string='Dosage')
    next_check_date = fields.Date(string='Next Check Date')
    animals_treated = fields.Integer(string='Animals Treated', default=1)

    # ── Cost ──────────────────────────────────────────────────────────────────

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    cost = fields.Monetary(string='Cost', currency_field='currency_id')

    # ── Result ────────────────────────────────────────────────────────────────

    result = fields.Selection(
        selection=[
            ('healthy',    'Healthy'),
            ('treated',    'Treated / Recovering'),
            ('critical',   'Critical'),
            ('dead',       'Animal Lost'),
        ],
        string='Result',
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft',    'Draft'),
            ('done',     'Done'),
        ],
        default='draft',
        required=True,
        tracking=True,
    )
    notes = fields.Text(string='Notes')

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_complete(self):
        self.write({'state': 'done'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})
