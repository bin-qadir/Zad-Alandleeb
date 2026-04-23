{
    'name': 'Construction Material Planning',
    'version': '18.0.3.0.0',
    'summary': 'Phase 3 — Material planning, material requests, procurement preparation',
    'description': (
        'Phase 3 — Material Planning & Requests.\n'
        'Links BOQ lines to products, planned quantities, stock availability,\n'
        'shortage visibility, and material request workflow.\n'
        'Prepares records for Phase 4 RFQ/PO integration.'
    ),
    'category': 'Construction',
    'author': 'bin-qadir',
    'license': 'LGPL-3',
    'depends': [
        'construction_boq',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'views/construction_material_plan_views.xml',
        'views/construction_material_request_views.xml',
        'views/construction_boq_line_ext_views.xml',
        'views/construction_project_ext_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
