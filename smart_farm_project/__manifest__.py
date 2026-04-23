{
    'name': 'Smart Farm Project',
    'version': '18.0.1.2.0',
    'summary': 'Farm project management for the Smart Farm system',
    'description': 'Manage farm projects and fields, linked to Odoo project tasks.',
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_base',
        'smart_farm_master',
        'project',
        'analytic',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/activity_lifecycle_stage_data.xml',
        'data/farm_project_type_data.xml',
        'views/farm_project_views.xml',
        'views/farm_field_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'smart_farm_project/static/src/css/farm_project_smart_buttons.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
