import logging
env['product.public.category'].search([]).action_generate_ai_icon()
env.cr.commit()
logging.info("ALL CATEGORY ICONS REGENERATED SUCCESSFULLY")
