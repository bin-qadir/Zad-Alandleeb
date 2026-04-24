from odoo import api, fields, models, _


class LivestockAnimal(models.Model):
    """Animal — individual record within a herd."""

    _name = 'livestock.animal'
    _description = 'Livestock Animal'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'herd_id, tag_number'
    _rec_name = 'display_name'

    tag_number = fields.Char(string='Tag / ID Number', required=True, tracking=True)
    name = fields.Char(string='Name', help='Optional individual name')
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name_field',
        store=True,
    )

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

    # ── Classification ────────────────────────────────────────────────────────

    species = fields.Selection(
        related='herd_id.species',
        store=True,
        readonly=True,
    )
    breed = fields.Char(string='Breed')
    gender = fields.Selection(
        selection=[
            ('male',   'Male'),
            ('female', 'Female'),
        ],
        string='Gender',
        required=True,
        tracking=True,
    )
    birth_date = fields.Date(string='Birth Date', tracking=True)
    age_months = fields.Integer(
        string='Age (months)',
        compute='_compute_age',
        store=False,
    )
    source = fields.Selection(
        selection=[
            ('born',      'Born in Herd'),
            ('purchased', 'Purchased'),
            ('transferred', 'Transferred'),
        ],
        string='Source',
        default='born',
    )

    # ── Physical ──────────────────────────────────────────────────────────────

    weight_initial_kg = fields.Float(string='Initial Weight (kg)', digits=(10, 2))
    weight_current_kg = fields.Float(string='Current Weight (kg)', digits=(10, 2))
    weight_target_kg = fields.Float(string='Target Weight (kg)', digits=(10, 2))

    # ── Mother / Breeding ─────────────────────────────────────────────────────

    mother_id = fields.Many2one(
        comodel_name='livestock.animal',
        string='Mother',
        domain="[('herd_id','=',herd_id),('gender','=','female')]",
        ondelete='set null',
    )

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('active',    'Active'),
            ('breeding',  'Breeding'),
            ('fattening', 'Fattening'),
            ('sick',      'Sick / Under Treatment'),
            ('sold',      'Sold'),
            ('dead',      'Dead / Culled'),
        ],
        default='active',
        required=True,
        tracking=True,
    )

    notes = fields.Text(string='Notes')

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('tag_number', 'name')
    def _compute_display_name_field(self):
        for rec in self:
            rec.display_name = (
                f'{rec.tag_number} — {rec.name}' if rec.name else rec.tag_number
            )

    def _compute_age(self):
        from datetime import date
        today = date.today()
        for rec in self:
            if rec.birth_date:
                delta = today - rec.birth_date
                rec.age_months = delta.days // 30
            else:
                rec.age_months = 0

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_set_breeding(self):
        self.write({'state': 'breeding'})

    def action_set_fattening(self):
        self.write({'state': 'fattening'})

    def action_set_sick(self):
        self.write({'state': 'sick'})

    def action_set_active(self):
        self.write({'state': 'active'})

    def action_mark_sold(self):
        self.write({'state': 'sold'})

    def action_mark_dead(self):
        self.write({'state': 'dead'})
