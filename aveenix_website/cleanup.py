import os
import re

# 1. Clean models/__init__.py
init_path = "/home/mittal/Workspace/19_odoo/custom/avee_custom_addons/aveenix_website/models/__init__.py"
with open(init_path, "r") as f:
    lines = f.readlines()
with open(init_path, "w") as f:
    f.writelines([l for l in lines if "import blog_blog" not in l])

# 2. Delete models/blog_blog.py
blog_py = "/home/mittal/Workspace/19_odoo/custom/avee_custom_addons/aveenix_website/models/blog_blog.py"
if os.path.exists(blog_py):
    os.remove(blog_py)

# 3. Clean views/website_config_views.xml
config_xml = "/home/mittal/Workspace/19_odoo/custom/avee_custom_addons/aveenix_website/views/website_config_views.xml"
with open(config_xml, "r") as f:
    c_xml = f.read()

c_xml = re.sub(r"<!-- blog\.blog form: Aveenix custom fields -->.*?</record>", "", c_xml, flags=re.DOTALL)
with open(config_xml, "w") as f:
    f.write(c_xml)

# 4. Clean controllers/main.py
main_py = "/home/mittal/Workspace/19_odoo/custom/avee_custom_addons/aveenix_website/controllers/main.py"
with open(main_py, "r") as f:
    c_main = f.read()

# Remove blog_categories logic from news_home
blog_logic = """
        # --- NEW LOGIC: Fetch Blog Posts Grouped by Category ---
        blog_posts = request.env['blog.post'].sudo().search([('website_published', '=', True)])
        categories_dict = {}
        for post in blog_posts:
            # Get the category from blog.blog model (e.g. Travel, Tech)
            cat_name = post.blog_id.name or 'General'
            if cat_name not in categories_dict:
                categories_dict[cat_name] = []
            
            # Extract background-image from cover_properties
            image_url = ""
            if post.cover_properties:
                try:
                    import json
                    cover_data = json.loads(post.cover_properties)
                    bg_img = cover_data.get('background-image', '')
                    if bg_img and 'url(' in bg_img:
                        image_url = bg_img.split("url(")[1].split(")")[0].strip('\"\\'')
                except Exception:
                    pass
            
            # Fallback image if none
            if not image_url:
                image_url = "https://images.unsplash.com/photo-1506929562872-bb421503ef21?auto=format&fit=crop&w=600&q=80"
                
            summary = post.subtitle or "Read our latest blog post to discover more insights and updates from our community."
                
            categories_dict[cat_name].append({
                'id': post.id,
                'category': cat_name.upper(),
                'title': post.name,
                'author': post.author_id.name or "Admin",
                'date': post.post_date.strftime('%B %d, %Y') if post.post_date else "",
                'image': image_url,
                'url': f"/news/blog/{post.id}",
                'summary': summary,
            })
            
        blog_categories = []
        for cat, posts in categories_dict.items():
            blog_categories.append({
                'name': cat,
                'posts': posts
            })
        # --------------------------------------------------------
"""
c_main = c_main.replace(blog_logic, "")
c_main = c_main.replace("            'blog_categories': blog_categories,\n", "")

# Remove blog_post_detail route
route_blog = r"    @http\.route\(\'/news/blog/<int:post_id>\'.*?return request\.render\(\'aveenix_website\.news_detail_template\', data\)"
c_main = re.sub(route_blog, "", c_main, flags=re.DOTALL)

with open(main_py, "w") as f:
    f.write(c_main)

# 5. Clean views/templates.xml
temp_xml = "/home/mittal/Workspace/19_odoo/custom/avee_custom_addons/aveenix_website/views/templates.xml"
with open(temp_xml, "r") as f:
    t_xml = f.read()

# Remove Blog Categories Full Width block
t_xml = re.sub(r"\s*<!-- Blog Categories Full Width -->.*?</div>\s*</div>", "", t_xml, flags=re.DOTALL)

# Revert news_detail_template changes
t_xml = t_xml.replace('<div t-attf-class="col-lg-#{\'10 mx-auto\' if article.get(\'is_blog\') else \'8\'}">', '<div class="col-lg-8">')
t_xml = t_xml.replace('<t t-if="not article.get(\'is_blog\')">\n                            <div class="col-lg-4">', '<div class="col-lg-4">')
t_xml = re.sub(r"\s*</div>\s*</t>\s*</div>\s*</div>\s*</div>\s*</t>\s*</template>", "\n                        </div>\n                    </div>\n                </div>\n            </div>\n        </t>\n    </template>", t_xml)


with open(temp_xml, "w") as f:
    f.write(t_xml)

print("Cleanup script complete!")
