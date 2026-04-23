{
    'name': 'Construction Procurement',
    'version': '18.0.4.0.0',
    'summary': 'Phase 4 — RFQ / Purchase Order / Delivery for construction procurement',
    'description': (
        'Phase 4 — Procurement Engine.\n'
        'Converts approved material requests into procurement records,\n'
        'creates and links native Odoo Purchase Orders, tracks deliveries,\n'
        'and feeds readiness progress back to BOQ / material plan lines.'
    ),
    'category': 'Construction',
    'author': 'bin-qadir',
    'license': 'LGPL-3',
    'depends': [
        'construction_material',
        'purchase',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'views/construction_procurement_views.xml',
        'views/construction_material_request_ext_views.xml',
        'views/construction_boq_line_ext_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
