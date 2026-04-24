"""
mythos.agent — Developer Agent extension
=========================================
Extends the agent_function Selection to include 'code_ui_development'
so the Developer Agent can be registered in the Mythos Agent registry
without modifying the base smart_farm_mythos_agents module.
"""
from odoo import fields, models


class MythosAgentDeveloperExt(models.Model):
    _inherit = 'mythos.agent'

    agent_function = fields.Selection(
        selection_add=[
            ('code_ui_development', 'Code & UI Development'),
        ],
        ondelete={'code_ui_development': 'cascade'},
    )
