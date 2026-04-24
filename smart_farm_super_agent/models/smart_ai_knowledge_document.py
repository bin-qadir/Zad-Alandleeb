"""
smart.ai.knowledge.document — Layer 6: RAG Knowledge Base
==========================================================
User-managed knowledge documents for future RAG/embedding integration.
"""
from odoo import fields, models


class SmartAiKnowledgeDocument(models.Model):
    _name        = 'smart.ai.knowledge.document'
    _description = 'AI Knowledge Document — Layer 6 RAG Engine'
    _order       = 'create_date desc'
    _rec_name    = 'name'

    name = fields.Char(string='Title', required=True)
    project_id = fields.Many2one(
        'farm.project',
        string='Project',
        ondelete='set null',
        index=True,
    )
    business_activity = fields.Selection(
        selection=[
            ('construction', 'Construction'),
            ('agriculture',  'Agriculture'),
            ('manufacturing','Manufacturing'),
            ('livestock',    'Livestock'),
        ],
        string='Business Activity',
        default='construction',
    )
    document_type = fields.Selection(
        selection=[
            ('contract',         'Contract'),
            ('boq',              'BOQ Document'),
            ('spec',             'Specification'),
            ('email',            'Email/Correspondence'),
            ('attachment',       'Attachment'),
            ('report',           'Report'),
            ('meeting_minutes',  'Meeting Minutes'),
            ('other',            'Other'),
        ],
        string='Document Type',
        required=True,
        default='other',
    )
    summary          = fields.Text(string='Document Summary', required=True)
    obligations      = fields.Text(string='Key Obligations')
    deadlines        = fields.Text(string='Deadlines & Milestones')
    risks            = fields.Text(string='Identified Risks')
    related_records  = fields.Text(string='Related Records (description)')
    attachment_ids   = fields.Many2many(
        comodel_name='ir.attachment',
        relation='sai_knowledge_attachment_rel',
        column1='doc_id',
        column2='att_id',
        string='Attachments',
    )
    created_by = fields.Many2one(
        'res.users',
        string='Created By',
        default=lambda self: self.env.user,
    )
    tags = fields.Char(
        string='Tags (comma-separated)',
        help='Future: used for semantic search/embeddings',
    )
    embedding_ready = fields.Boolean(
        string='Ready for Embedding',
        default=False,
        help='Mark when document is ready for vector embedding in future RAG implementation',
    )
