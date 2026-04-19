{
    'name': 'Smart Farm Costing',
    'version': '18.0.1.1.0',
    'summary': 'Material, labor and overhead costing for BOQ lines',
    'description': (
        'Adds full cost analysis to each BOQ line: materials, labor, '
        'overhead, cost totals, profit, and margin percentage.'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_base',
        'smart_farm_master',
        'smart_farm_boq',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/farm_boq_line_costing_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
