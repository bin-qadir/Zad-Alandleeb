{
    'name': 'Smart Farm Material Request',
    'version': '18.0.1.0.0',
    'summary': 'Material Request → RFQ → PO → Receipt cost tracking linked to BOQ and Job Orders',
    'description': (
        'Full procurement cycle for Smart Farm construction workflow:\n\n'
        '1. MATERIAL REQUEST\n'
        '   Raise requests at Job Order level, tied to BOQ lines.\n'
        '   Validates requested qty against BOQ contract qty minus already-requested.\n\n'
        '2. APPROVAL WORKFLOW\n'
        '   Draft → Submit → PM Approve/Reject → PO created on approval.\n\n'
        '3. RFQ / PURCHASE ORDER\n'
        '   Approved MRs auto-generate Purchase Orders grouped by vendor.\n'
        '   PO carries farm_project_id + material_request_id links.\n\n'
        '4. RECEIPT & ACTUAL COST\n'
        '   received_qty tracked per line; actual_cost = received_qty × unit_price.\n'
        '   MR state progresses: approved → rfq → ordered → received.\n\n'
        '5. DASHBOARD KPIS\n'
        '   Pending / Approved / Rejected request counts + total procurement cost\n'
        '   added to the Executive Dashboard.\n'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_execution',       # farm.job.order, farm.boq.line
        'smart_farm_procurement',     # purchase.order.farm_project_id
        'smart_farm_dashboard',       # farm.dashboard (for KPI extension)
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/farm_material_request_views.xml',
        'views/farm_job_order_inherit.xml',
        'views/farm_dashboard_inherit.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
