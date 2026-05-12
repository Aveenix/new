import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import gen_po

trans = gen_po.TRANSLATIONS['fr']
missing = [(m, gen_po.translate_fragment(m, trans)) for m in gen_po.strings_ordered if not gen_po.translate_fragment(m, trans)]
print(f'Missing for fr: {len(missing)}')
for m, _ in missing:
    print('  MISS:', repr(m[:100]))

print()
print('Sample translations:')
samples = ['My Account', 'For You', 'Best Sellers', 'Add to Cart', 'Customer Service', 'Dark', 'Summer Electronics', 'Log Out']
for s in samples:
    matches = [k for k in gen_po.strings_map if s in k]
    for k in matches[:1]:
        r = gen_po.translate_fragment(k, trans)
        print(f'  OK={bool(r)} key={repr(k[:60])}')
        if r:
            print(f'       => {repr(r[:60])}')
