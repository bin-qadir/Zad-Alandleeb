"""
mythos.developer.task
======================
Reviewable task queue produced by the Developer Agent scan actions.

Safety rules:
  • No code is auto-written.
  • No Studio views are auto-modified.
  • Every task requires human review before any action is taken.
  • BOQ / Costing / Execution are never touched unless the user
    explicitly approves a task that targets those modules.
"""
import os
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

# ── Selection constants ────────────────────────────────────────────────────────

TASK_TYPE_SELECTION = [
    ('python_fix',          'Python Fix'),
    ('xml_view_fix',        'XML View Fix'),
    ('ui_layout',           'UI Layout'),
    ('studio_cleanup',      'Studio Cleanup'),
    ('menu_action_fix',     'Menu / Action Fix'),
    ('refactor_suggestion', 'Refactor Suggestion'),
]

TASK_STATE_SELECTION = [
    ('draft',    'Draft'),
    ('reviewed', 'Reviewed'),
    ('approved', 'Approved'),
    ('applied',  'Applied'),
    ('rejected', 'Rejected'),
]

# Modules the Developer Agent will NEVER auto-touch
PROTECTED_MODULES = {
    'smart_farm_boq',
    'smart_farm_costing',
    'smart_farm_boq_analysis',
    'smart_farm_execution',
    'smart_farm_sale_contract',
    'smart_farm_contract',
}


class MythosDeveloperTask(models.Model):
    """Developer Agent task — produced by scans, reviewed by humans."""

    _name        = 'mythos.developer.task'
    _description = 'Mythos Developer Task'
    _order       = 'create_date desc'
    _inherit     = ['mail.thread', 'mail.activity.mixin']

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Task',
        required=True,
        tracking=True,
    )
    task_type = fields.Selection(
        selection=TASK_TYPE_SELECTION,
        string='Type',
        required=True,
        default='refactor_suggestion',
        tracking=True,
    )
    state = fields.Selection(
        selection=TASK_STATE_SELECTION,
        string='State',
        default='draft',
        required=True,
        tracking=True,
    )

    # ── Target ────────────────────────────────────────────────────────────────

    target_module = fields.Char(
        string='Target Module',
        help='Custom module name (e.g. smart_farm_boq)',
    )
    target_model = fields.Char(
        string='Target Model',
        help='Odoo model technical name (e.g. farm.boq)',
    )
    target_view_id = fields.Many2one(
        comodel_name='ir.ui.view',
        string='Target View',
        ondelete='set null',
        help='Specific UI view affected by this task.',
    )

    # ── Analysis ──────────────────────────────────────────────────────────────

    issue_description = fields.Text(
        string='Issue Description',
        help='What the Developer Agent found or what needs attention.',
    )
    proposed_solution = fields.Text(
        string='Proposed Solution',
        help='Suggested fix or action. Always requires human review.',
    )
    claude_prompt = fields.Text(
        string='Claude Prompt',
        readonly=True,
        copy=False,
        help='Auto-generated prompt ready to paste into Claude Code.',
    )

    # ── Safety flag ───────────────────────────────────────────────────────────

    is_protected_module = fields.Boolean(
        string='Protected Module',
        compute='_compute_is_protected_module',
        store=True,
        help='True when target_module is a protected BOQ/Costing/Execution module.',
    )

    @api.depends('target_module')
    def _compute_is_protected_module(self):
        for rec in self:
            rec.is_protected_module = (rec.target_module or '') in PROTECTED_MODULES

    # ── Workflow actions ──────────────────────────────────────────────────────

    def action_mark_reviewed(self):
        self.write({'state': 'reviewed'})

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_reject(self):
        self.write({'state': 'rejected'})

    def action_mark_applied(self):
        self.write({'state': 'applied'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    # ── Generate Claude Prompt ────────────────────────────────────────────────

    def action_generate_claude_prompt(self):
        self.ensure_one()
        branch = 'Dev-ai-work-rev-00'

        task_type_label = dict(TASK_TYPE_SELECTION).get(self.task_type, self.task_type)

        prompt_lines = [
            f'# Developer Agent Task — Claude Code Prompt',
            f'',
            f'**Branch**: `{branch}`',
            f'**Task Type**: {task_type_label}',
            f'**Target Module**: {self.target_module or "N/A"}',
            f'**Target Model**: {self.target_model or "N/A"}',
        ]

        if self.target_view_id:
            prompt_lines.append(
                f'**Target View**: {self.target_view_id.name} '
                f'(XMLID: {self.target_view_id.key or "unknown"})'
            )

        prompt_lines += [
            f'',
            f'## Problem',
            self.issue_description or '_No description provided._',
            f'',
            f'## Required Fix',
            self.proposed_solution or '_No solution provided yet — please fill in before using this prompt._',
            f'',
            f'## ⚠️ CRITICAL WARNINGS',
            f'- Work **only** on branch: `{branch}`',
            f'- Do **NOT** break the existing workflow',
            f'- Do **NOT** change BOQ, Costing, Analysis, Templates, Quantities, Execution, or Agents',
            f'  unless this task explicitly targets those modules',
            f'- Produce minimal, targeted changes only',
            f'- Return the commit hash when done',
        ]

        if self.is_protected_module:
            prompt_lines.insert(
                -1,
                f'\n## 🛑 PROTECTED MODULE WARNING\n'
                f'`{self.target_module}` is a **protected module**.\n'
                f'Only proceed after explicit user confirmation and task approval.',
            )

        self.claude_prompt = '\n'.join(prompt_lines)
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Claude Prompt Generated'),
                'message': _('The prompt is ready in the "Claude Prompt" field below.'),
                'type':    'success',
                'sticky':  False,
            },
        }

    # ── Scan Code ────────────────────────────────────────────────────────────

    @api.model
    def action_scan_modules(self):
        """
        Scan all custom modules in /home/odoo/src/user/.
        Creates a reviewer task for each finding.
        Read-only operation — no files are modified.
        """
        user_path = '/home/odoo/src/user'
        modules_found = []
        for entry in sorted(os.listdir(user_path)):
            full = os.path.join(user_path, entry)
            if (os.path.isdir(full)
                    and os.path.exists(os.path.join(full, '__manifest__.py'))):
                modules_found.append(entry)

        created = 0
        for module_name in modules_found:
            module_path = os.path.join(user_path, module_name)

            # Count source files
            py_count = sum(
                1 for root, _dirs, files in os.walk(module_path)
                for fn in files
                if fn.endswith('.py') and '__pycache__' not in root
            )
            xml_count = sum(
                1 for root, _dirs, files in os.walk(module_path)
                for fn in files
                if fn.endswith('.xml')
            )
            has_security = os.path.exists(
                os.path.join(module_path, 'security', 'ir.model.access.csv')
            )

            issues = []
            task_type = 'refactor_suggestion'

            if not has_security:
                issues.append('⚠ Missing security/ir.model.access.csv')
                task_type = 'python_fix'

            if not issues:
                issues.append(
                    f'Module structure OK.\n'
                    f'  Python files : {py_count}\n'
                    f'  XML files    : {xml_count}\n'
                    f'  Security     : ✓\n'
                )

            # Skip if a non-closed task already exists for this module+type
            existing = self.search([
                ('target_module', '=', module_name),
                ('task_type', '=', task_type),
                ('state', 'not in', ['applied', 'rejected']),
            ], limit=1)
            if existing:
                continue

            self.create({
                'name':              f'[Scan] {module_name}',
                'task_type':         task_type,
                'target_module':     module_name,
                'issue_description': '\n'.join(issues),
            })
            created += 1

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Code Scan Complete'),
                'message': _(
                    'Scanned %(n)s modules. %(c)s new task(s) created.',
                    n=len(modules_found), c=created,
                ),
                'type':    'success',
                'sticky':  False,
            },
        }

    # ── Scan Studio Views ─────────────────────────────────────────────────────

    @api.model
    def action_scan_studio_views(self):
        """
        Scan ir.ui.view records created or modified by Odoo Studio.
        Creates a reviewer task per Studio view found.
        Read-only operation — no views are modified.
        """
        IrModelData = self.env['ir.model.data']

        # Studio-created views appear in ir.model.data with module='studio_customization'
        studio_data = IrModelData.search([
            ('module', '=', 'studio_customization'),
            ('model', '=', 'ir.ui.view'),
        ])
        studio_view_ids = studio_data.mapped('res_id')
        studio_views = self.env['ir.ui.view'].browse(studio_view_ids).exists()

        created = 0
        for view in studio_views:
            existing = self.search([
                ('target_view_id', '=', view.id),
                ('task_type', '=', 'studio_cleanup'),
                ('state', 'not in', ['applied', 'rejected']),
            ], limit=1)
            if existing:
                continue

            self.create({
                'name':              f'[Studio] {view.name or view.key or view.id}',
                'task_type':         'studio_cleanup',
                'target_model':      view.model or '',
                'target_view_id':    view.id,
                'issue_description': (
                    f'View created/modified by Odoo Studio.\n'
                    f'  Model     : {view.model or "N/A"}\n'
                    f'  View type : {view.type or "N/A"}\n'
                    f'  Key       : {view.key or "N/A"}\n'
                    f'  Active    : {view.active}\n\n'
                    f'Review whether this customization can be replaced by\n'
                    f'a proper XML view in a custom module.'
                ),
            })
            created += 1

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Studio Scan Complete'),
                'message': _(
                    'Found %(n)s Studio view(s). %(c)s new task(s) created.',
                    n=len(studio_views), c=created,
                ),
                'type':    'success' if created >= 0 else 'warning',
                'sticky':  False,
            },
        }
