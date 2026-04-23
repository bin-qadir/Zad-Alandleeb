from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ConstructionMaterialRequest(models.Model):
    _name = 'construction.material.request'
    _description = 'Construction Material Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, name desc'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )

    # ── Project / Structure ───────────────────────────────────────────────────

    project_id = fields.Many2one(
        comodel_name='construction.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    division_id = fields.Many2one(
        comodel_name='construction.division',
        string='Division',
        ondelete='set null',
        domain="[('project_id', '=', project_id)]",
        tracking=True,
    )
    subdivision_id = fields.Many2one(
        comodel_name='construction.subdivision',
        string='Subdivision',
        ondelete='set null',
        domain="[('division_id', '=', division_id)]",
        tracking=True,
    )

    # ── Requestor / Date ──────────────────────────────────────────────────────

    requested_by = fields.Many2one(
        comodel_name='res.users',
        string='Requested By',
        default=lambda self: self.env.uid,
        ondelete='set null',
        tracking=True,
    )
    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',                   'Draft'),
            ('submitted',               'Submitted'),
            ('approved',                'Approved'),
            ('rejected',                'Rejected'),
            ('converted_to_procurement','Converted to Procurement'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )

    # ── Lines ─────────────────────────────────────────────────────────────────

    line_ids = fields.One2many(
        comodel_name='construction.material.request.line',
        inverse_name='request_id',
        string='Request Lines',
    )
    line_count = fields.Integer(
        string='Lines',
        compute='_compute_line_count',
    )

    # ── Summary totals ────────────────────────────────────────────────────────

    total_requested = fields.Float(
        string='Total Items',
        compute='_compute_summary',
        digits=(16, 2),
    )
    shortage_line_count = fields.Integer(
        string='Lines with Shortage',
        compute='_compute_summary',
    )

    # ── Notes ─────────────────────────────────────────────────────────────────

    notes = fields.Text(string='Notes')

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.depends('line_ids.requested_qty', 'line_ids.shortage_qty')
    def _compute_summary(self):
        for rec in self:
            rec.total_requested = sum(rec.line_ids.mapped('requested_qty'))
            rec.shortage_line_count = len(
                rec.line_ids.filtered(lambda l: l.shortage_qty > 0)
            )

    # ── ORM ───────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'construction.material.request'
                ) or _('New')
        return super().create(vals_list)

    # ── State transitions ─────────────────────────────────────────────────────

    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(
                    _('Cannot submit a material request with no lines.\n'
                      'Add at least one product line before submitting.')
                )
        self.write({'state': 'submitted'})

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_reject(self):
        self.write({'state': 'rejected'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_convert_to_procurement(self):
        """
        Mark the request as converted to procurement.
        Phase 4 will create actual RFQ/PO records here.
        """
        for rec in self:
            if rec.state != 'approved':
                raise UserError(
                    _('Only approved requests can be converted to procurement.\n'
                      'Request "%s" is in state "%s".') % (rec.name, rec.state)
                )
        self.write({'state': 'converted_to_procurement'})

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_open_material_plans(self):
        """Open all material plan lines that generated this request's lines."""
        self.ensure_one()
        plan_ids = self.line_ids.filtered(
            lambda l: l.material_plan_id
        ).mapped('material_plan_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Material Plans — %s') % self.name,
            'res_model': 'construction.material.plan',
            'view_mode': 'list,form',
            'domain': [('id', 'in', plan_ids)],
        }
