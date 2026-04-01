# -*- coding: utf-8 -*-
{
    'name': 'Task BOQ Advanced',
    'version': '18.0.1.0.0',
    'summary': 'Advanced BOQ, Costing, RFQ, Quotation, and AI Alerts for Projects',
    'description': '''
Task BOQ Advanced
=================
Professional BOQ management for Odoo 18:
- BOQ lines under projects/tasks
- Material / labor / overhead costing
- RFQ creation from BOQ resources
- Quotation creation from BOQ lines
- AI alerts for delay, loss, procurement
''',
    'category': 'Project',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'project',
        'product',
        'uom',
        'purchase',
        'sale_management',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/boq_line_views.xml',
        'views/ai_alert_views.xml',
        'views/project_task_views.xml',
        'views/project_project_views.xml',
        'views/menu_views.xml',
        'data/ai_cron.xml',
    ],
    'installable': True,
    'application': True,
}
