{
    'name': 'Construction Project',
    'version': '18.0.1.0.0',
    'summary': 'Construction project core — projects, divisions, subdivisions',
    'description': (
        'Phase 1 — Construction Project Core.\n'
        'Establishes the base architecture for the full construction ERP:\n'
        'project identity, division structure, subdivision structure,\n'
        'analytic account linkage, and Odoo project linkage.'
    ),
    'category': 'Construction',
    'author': 'bin-qadir',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'project',
        'analytic',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/construction_project_views.xml',
        'views/construction_division_views.xml',
        'views/construction_subdivision_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,  # Hidden from Apps dashboard; managed via smart_farm_construction
    'auto_install': False,
}
