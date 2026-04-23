{
    'name': 'Construction BOQ & Costing',
    'version': '18.0.2.0.0',
    'summary': 'Phase 2 — BOQ document, cost structure, pricing and margin engine',
    'description': (
        'Phase 2 — BOQ & Costing Engine.\n'
        'Full Bill of Quantities with per-line cost breakdown:\n'
        'material, labor, subcontract, equipment, tools, overhead.\n'
        'Automatic cost aggregation, sale pricing, and margin computation.'
    ),
    'category': 'Construction',
    'author': 'bin-qadir',
    'license': 'LGPL-3',
    'depends': [
        'construction_project',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/construction_boq_line_views.xml',
        'views/construction_boq_views.xml',
        'views/construction_project_ext_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
