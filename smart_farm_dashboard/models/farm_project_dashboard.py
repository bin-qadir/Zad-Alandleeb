"""
farm.project extension — dashboard navigation helpers
=====================================================

Adds action_open_project_construction_dashboard() to farm.project so that
the Level 1 kanban card's overlay button can open the Level 2 per-project
dashboard when a project card is clicked.
"""
from odoo import models, _


class FarmProjectDashboardMixin(models.Model):
    _inherit = 'farm.project'

    def action_open_project_construction_dashboard(self):
        """Open the Level 2 Construction Project Dashboard for this project."""
        self.ensure_one()
        return (
            self.env['farm.construction.project.dashboard']
            .action_open_for_project(self.id)
        )
