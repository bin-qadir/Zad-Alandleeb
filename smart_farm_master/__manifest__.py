{
    'name': 'Smart Farm Master',
    'version': '18.0.1.0.0',
    'summary': 'Master data module for the Smart Farm system',
    'description': 'Provides master data (lookup) models for the Smart Farm system.',
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': ['smart_farm_base'],
    'data': [
        'security/ir.model.access.csv',
        'views/base_views.xml',
        'views/menu.xml',
        'data/farm_crop_type_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
