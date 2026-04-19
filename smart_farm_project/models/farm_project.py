from odoo import api, fields, models, _


class FarmProject(models.Model):
    _name = 'farm.project'
    _description = 'Farm Project'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(string='Name', required=True, tracking=True)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('running', 'Running'),
            ('done', 'Done'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )

    # ── Project Classification ─────────────────────────────────────────────────
    project_type = fields.Selection(
        selection=[
            ('irrigation',   'Irrigation'),
            ('construction', 'Construction'),
            ('agriculture',  'Agriculture'),
            ('mixed',        'Mixed'),
        ],
        string='Project Type',
        tracking=True,
    )
    project_manager_id = fields.Many2one(
        comodel_name='res.users',
        string='Project Manager',
        ondelete='set null',
        tracking=True,
    )
    project_tag_ids = fields.Many2many(
        comodel_name='smart.farm.tag',
        relation='farm_project_tag_rel',
        column1='project_id',
        column2='tag_id',
        string='Tags',
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        ondelete='set null',
        copy=False,
    )

    # ── Links ─────────────────────────────────────────────────────────────────
    odoo_project_id = fields.Many2one(
        comodel_name='project.project',
        string='Odoo Project',
        ondelete='set null',
        tracking=True,
    )

    # ── Schedule ──────────────────────────────────────────────────────────────
    start_date = fields.Date(string='Start Date', tracking=True)
    end_date = fields.Date(string='End Date', tracking=True)

    # ── Description ───────────────────────────────────────────────────────────
    description = fields.Text(string='Description')

    # ── Location ──────────────────────────────────────────────────────────────
    country_id = fields.Many2one(
        comodel_name='res.country',
        string='Country',
        ondelete='set null',
    )
    state_id = fields.Many2one(
        comodel_name='res.country.state',
        string='State / Region',
        domain="[('country_id', '=', country_id)]",
        ondelete='set null',
    )
    city = fields.Char(string='City')
    location_text = fields.Text(string='Location Details')
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))

    # ── Area ──────────────────────────────────────────────────────────────────
    total_project_area = fields.Float(
        string='Total Area (ha)', digits=(16, 4),
    )
    cultivated_area = fields.Float(
        string='Cultivated Area (ha)', digits=(16, 4),
    )
    builtup_area = fields.Float(
        string='Built-up Area (ha)', digits=(16, 4),
    )

    # ── Consists ──────────────────────────────────────────────────────────────
    consists_notes = fields.Text(string='Project Consists of')

    # ── Documents ─────────────────────────────────────────────────────────────
    document_notes = fields.Text(string='Document Notes')

    # ── Drawings ──────────────────────────────────────────────────────────────
    drawing_notes = fields.Text(string='Drawing Notes')

    # ── Teams ─────────────────────────────────────────────────────────────────
    team_member_ids = fields.Many2many(
        comodel_name='res.users',
        relation='farm_project_team_rel',
        column1='project_id',
        column2='user_id',
        string='Team Members',
    )

    # ── Zones ─────────────────────────────────────────────────────────────────
    zone_notes = fields.Text(string='Zone Notes')

    # ── Fields relation ───────────────────────────────────────────────────────
    field_ids = fields.One2many(
        comodel_name='farm.field',
        inverse_name='project_id',
        string='Fields',
    )

    # ── Stat button ───────────────────────────────────────────────────────────
    field_count = fields.Integer(
        string='Field Count',
        compute='_compute_field_count',
    )

    @api.depends('field_ids')
    def _compute_field_count(self):
        for rec in self:
            rec.field_count = len(rec.field_ids)

    def action_open_fields(self):
        """Open Farm Fields filtered to this project."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fields — %s') % self.name,
            'res_model': 'farm.field',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
