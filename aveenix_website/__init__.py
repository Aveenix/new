# -*- coding: utf-8 -*-
from . import models
from . import controllers


def post_init_hook(env):
    """Ensure every active currency has a selectable website pricelist so the
    header currency switcher lists them all, with prices auto-converted."""
    for website in env['website'].search([]):
        website._av_ensure_currency_pricelists()