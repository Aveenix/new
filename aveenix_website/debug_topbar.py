import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from lxml import etree
import gen_po

# Manually run process_node on the <a> element to trace what happens
tree = etree.parse('views/layout.xml')
found_a = None
for template in tree.getroot().iter('template'):
    if template.get('id') == 'aveenix_header':
        for el in template.iter():
            tag = el.tag if isinstance(el.tag, str) else ''
            cls = el.get('class', '')
            if tag == 'a' and 'av-topbar-link' in cls and not el.get('href','').startswith('/web'):
                href = el.get('href','')
                if '/my/account' in href:
                    found_a = el
                    break
        break

if found_a is not None:
    print('Found a.av-topbar-link href=/my/account')
    print('  a.text:', repr(found_a.text))
    print('  children:', list(found_a))
    for c in found_a:
        print('  child:', c.tag, 'tail:', repr(c.tail))
    print()
    print('  local_tag:', gen_po.local_tag(found_a))
    print('  has_directive:', gen_po.has_directive(found_a))
    print('  translatable(a):', gen_po.translatable(found_a))
    print()

    children = list(found_a)
    print('  hastext(a, 0):', gen_po.hastext(found_a, 0))

    if children:
        i_el = children[0]
        print('  translatable(i):', gen_po.translatable(i_el))
        print('  hastext(i, 0):', gen_po.hastext(i_el, 0))
        print('  hastext(a, 1):', gen_po.hastext(found_a, 1))

    # Now simulate process_node
    print()
    print('Simulating process_node on <a>:')
    # Clear and re-add
    old_ordered = gen_po.strings_ordered[:]
    old_map = {k: v.copy() for k, v in gen_po.strings_map.items()}
    gen_po.strings_ordered.clear()
    gen_po.strings_map.clear()
    gen_po.process_node(found_a, 'aveenix_website.aveenix_header')
    print('  Generated strings:')
    for s in gen_po.strings_ordered:
        print('   ', repr(s[:100]))
    # restore
    gen_po.strings_ordered.clear()
    gen_po.strings_map.clear()
    gen_po.strings_ordered.extend(old_ordered)
    gen_po.strings_map.update(old_map)
