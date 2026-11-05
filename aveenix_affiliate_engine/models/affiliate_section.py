"""News sections, and the per-category switch for affiliate placement."""

from odoo import api, fields, models


class AffiliateSection(models.Model):
    """One Aveenix News section that offers can be targeted at.

    `code` mirrors `aveenix.news.category` — the selection is read off that
    field at runtime, so the two lists cannot drift apart as sections are added.

    Archiving a section is the "disable this category" control the brief asks
    for, and it acts in both directions: the matcher will not create placements
    for articles in an archived section, and placements already made there stop
    rendering. That makes it a safe emergency switch for one topic (say, a
    sensitive news category) without touching the rest of the site.
    """

    _name = 'affiliate.section'
    _description = 'Affiliate Section'
    _order = 'name'

    def _av_section_selection(self):
        return self.env['aveenix.news']._fields['category'].selection

    code = fields.Selection(
        selection='_av_section_selection',
        string='News Category',
        required=True,
        help='The aveenix.news category this section gates.',
    )
    name = fields.Char(string='Name', required=True, translate=True)
    active = fields.Boolean(
        string='Allow Affiliate Offers',
        default=True,
        help='Uncheck to stop placing affiliate offers in this category entirely. '
             'Existing placements in it stop showing immediately.',
    )
    offer_ids = fields.Many2many(
        comodel_name='affiliate.offer',
        relation='affiliate_offer_section_rel',
        column1='section_id',
        column2='offer_id',
        string='Offers',
    )
    offer_count = fields.Integer(string='Offer Count', compute='_compute_offer_count')

    _code_uniq = models.Constraint(
        'UNIQUE(code)',
        'There is already a section for this news category.',
    )

    @api.depends('offer_ids')
    def _compute_offer_count(self):
        for section in self:
            section.offer_count = len(section.offer_ids)

    @api.model
    def _av_allows(self, category):
        """True when offers may be placed in `category`.

        A category with no section record at all is allowed: the seed data
        covers every section that exists today, so a missing row means a newly
        added news category rather than a deliberate opt-out, and silently
        refusing to monetise it would be the harder failure to notice.
        """
        if not category:
            return False
        sections = self.with_context(active_test=False).search([('code', '=', category)])
        if not sections:
            return True
        return any(sections.mapped('active'))
