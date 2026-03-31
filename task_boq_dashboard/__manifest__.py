{
    'name': 'Task BOQ Executive Dashboard',
    'version': '18.0.1.0.0',
    'summary': 'Standalone executive dashboard for BOQ costing, profitability, inventory and AI alerts',
    'depends': ['project', 'task_boq_advanced'],
    'data': ['security/ir.model.access.csv', 'views/boq_dashboard_views.xml', 'views/menu.xml'],
    'installable': True,
    'license': 'LGPL-3',
}
