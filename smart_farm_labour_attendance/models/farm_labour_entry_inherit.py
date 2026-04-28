"""
farm.labour.entry — Attendance linkage extension.

Adds optional back-reference fields from farm.labour.entry to the
attendance sheet and line that generated it.  None of these fields
are required — existing records are unaffected.
"""
from odoo import fields, models


class FarmLabourEntryAttendance(models.Model):
    _inherit = 'farm.labour.entry'

    # ── Attendance back-references ────────────────────────────────────────────
    attendance_id = fields.Many2one(
        'farm.labour.attendance',
        string='Attendance Sheet',
        ondelete='set null',
        index=True,
        help='Daily attendance sheet that generated this entry.',
    )
    attendance_line_id = fields.Many2one(
        'farm.labour.attendance.line',
        string='Attendance Line',
        ondelete='set null',
        index=True,
    )

    # ── Time (copied from attendance line) ───────────────────────────────────
    check_in  = fields.Datetime(string='Check In')
    check_out = fields.Datetime(string='Check Out')

    # ── Signature and GPS (copied from worker line) ──────────────────────────
    worker_signature = fields.Binary(
        string='Worker Signature',
        attachment=True,
    )
    worker_gps_lat = fields.Float(string='GPS Latitude',  digits=(10, 7))
    worker_gps_lng = fields.Float(string='GPS Longitude', digits=(10, 7))
