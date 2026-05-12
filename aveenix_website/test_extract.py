from lxml import etree; import gen_po; xml='<button t-att-id=\
1\><i/><span>Add to Cart</span></button>'; node=etree.fromstring(xml); gen_po.process_node(node, 'foo'); print(gen_po.strings_ordered)
