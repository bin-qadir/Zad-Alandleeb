from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ConstructionBOQ(models.Model):
    _name = 'construction.boq'
    _description = 'Construction Bill of Quantities'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'project_id, revision_no desc, id desc'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='BOQ Name',
        required=True,
        tracking=True,
    )
    project_id = fields.Many2one(
        comodel_name='construction.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    revision_no = fields.Integer(
        string='Revision',
        default=0,
        copy=False,
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        default=fields.Date.context_today,
        tracking=True,
    )

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',     'Draft'),
            ('reviewed',  'Reviewed'),
            ('approved',  'Approved'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )

    # ── Currency ──────────────────────────────────────────────────────────────

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='project_id.currency_id',
        store=True,
        readonly=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────

    notes = fields.Html(string='Notes')

    # ── Lines ─────────────────────────────────────────────────────────────────

    line_ids = fields.One2many(
        comodel_name='construction.boq.line',
        inverse_name='boq_id',
        string='BOQ Lines',
    )
    line_count = fields.Integer(
        string='Lines',
        compute='_compute_line_count',
    )

    # ── Financial totals ──────────────────────────────────────────────────────

    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )
    total_sale = fields.Float(
        string='Total Sale',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )
    profit_amount = fields.Float(
        string='Profit',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )
    profit_margin_percent = fields.Float(
        string='Margin %',
        compute='_compute_totals',
        store=True,
        digits=(16, 2),
    )

    # ── Cost breakdown totals ─────────────────────────────────────────────────

    total_material_cost = fields.Float(
        string='Total Material',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )
    total_labor_cost = fields.Float(
        string='Total Labor',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )
    total_subcontract_cost = fields.Float(
        string='Total Subcontract',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )
    total_equipment_cost = fields.Float(
        string='Total Equipment',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )
    total_tools_cost = fields.Float(
        string='Total Tools',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )
    total_overhead_cost = fields.Float(
        string='Total Overhead',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )
    total_other_cost = fields.Float(
        string='Total Other',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.depends(
        'line_ids.total_cost',
        'line_ids.total_sale',
        'line_ids.planned_material_cost',
        'line_ids.planned_labor_cost',
        'line_ids.planned_subcontract_cost',
        'line_ids.planned_equipment_cost',
        'line_ids.planned_tools_cost',
        'line_ids.planned_overhead_cost',
        'line_ids.planned_other_cost',
    )
    def _compute_totals(self):
        for rec in self:
            lines = rec.line_ids
            rec.total_cost = sum(lines.mapped('total_cost'))
            rec.total_sale = sum(lines.mapped('total_sale'))
            rec.profit_amount = rec.total_sale - rec.total_cost
            rec.profit_margin_percent = (
                (rec.profit_amount / rec.total_sale * 100.0)
                if rec.total_sale else 0.0
            )
            rec.total_material_cost = sum(lines.mapped('planned_material_cost'))
            rec.total_labor_cost = sum(lines.mapped('planned_labor_cost'))
            rec.total_subcontract_cost = sum(lines.mapped('planned_subcontract_cost'))
            rec.total_equipment_cost = sum(lines.mapped('planned_equipment_cost'))
            rec.total_tools_cost = sum(lines.mapped('planned_tools_cost'))
            rec.total_overhead_cost = sum(lines.mapped('planned_overhead_cost'))
            rec.total_other_cost = sum(lines.mapped('planned_other_cost'))

    # ── State transitions ─────────────────────────────────────────────────────

    def action_submit_review(self):
        self.write({'state': 'reviewed'})

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_revise(self):
        """Create a new draft revision of this BOQ (copy with incremented revision_no)."""
        self.ensure_one()
        new_rev = self.revision_no + 1
        new_boq = self.copy(default={
            'state': 'draft',
            'revision_no': new_rev,
            'name': '%s (Rev %s)' % (
                self.name.split(' (Rev ')[0],
                new_rev,
            ),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQ Revision %s') % new_rev,
            'res_model': 'construction.boq',
            'view_mode': 'form',
            'res_id': new_boq.id,
        }

    # ── Smart button action ───────────────────────────────────────────────────

    def action_open_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQ Lines — %s') % self.name,
            'res_model': 'construction.boq.line',
            'view_mode': 'list,form',
            'domain': [('boq_id', '=', self.id)],
            'context': {
                'default_boq_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }
