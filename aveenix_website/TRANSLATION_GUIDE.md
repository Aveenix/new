# Translation Guide — aveenix_website

This guide explains how to add or fix translations for the `aveenix_website` Odoo 19 custom module.

---

## How the system works

Odoo loads `.po` files from `i18n/` on module install/update. Each entry maps an English source string (msgid) to a translated string (msgstr). The file `gen_po.py` generates all `.po` files automatically from the view XML sources.

**Do not edit `.po` files by hand.** Edit `gen_po.py` and regenerate.

### Key facts about Odoo's translation model

- Translations target `ir.ui.view.arch_db` records — the stored QWeb template XML.
- For elements with **only text** (e.g. `<h2>Shop Now</h2>`), the msgid is the plain text: `Shop Now`.
- For elements with **mixed content** (text + inline child elements like `<i>`, `<br/>`), Odoo groups them into a single XML-fragment msgid:
  - Source: `<a><i class="fa fa-user-circle"/> My Account</a>`
  - msgid: `<i class="fa fa-user-circle"/> My Account`
  - msgstr: `<i class="fa fa-user-circle"/> 我的账户`
- The msgstr for XML fragments must preserve the exact same XML structure — only text content changes.
- Every entry **must** have `#. module: aveenix_website` and `#: model_terms:ir.ui.view,arch_db:aveenix_website.<template_id>`.

---

## Supported languages

| File | Language | Code |
|------|----------|------|
| `i18n/zh_CN.po` | Chinese Simplified | `zh_CN` |
| `i18n/fr.po` | French | `fr` |
| `i18n/de.po` | German | `de` |
| `i18n/it.po` | Italian | `it` |
| `i18n/ja.po` | Japanese | `ja` |
| `i18n/pt.po` | Portuguese | `pt` |
| `i18n/es.po` | Spanish | `es` |

To add a new language, see [Adding a new language](#adding-a-new-language).

---

## Step-by-step: add translations for new strings

### 1. Find untranslated strings

Run `gen_po.py` and look at the coverage count:

```
cd c:\odoo\odoo19\custom\aveenix_website
python gen_po.py
```

Output example:
```
Extracted 108 strings
Written: zh_CN.po  (92/108 translated)
```

To list every untranslated string for a language:

```python
import gen_po
missing = [m for m, _ in gen_po.strings_data if not gen_po.translate_fragment(m, gen_po.TRANSLATIONS['zh_CN'])]
for m in missing:
    print(repr(m[:80]))
```

### 2. Identify what the string looks like in the XML

Open `views/templates.xml` or `views/layout.xml` and search for the English text. Note:

- **Plain text node** — element has no child elements: `<span>Add to Cart</span>` → key is `Add to Cart`
- **Mixed content** — element has inline children (`<i>`, `<br/>`): `<button><i class="fa fa-cart"/> Add to Cart</button>` → key is `<i class="fa fa-cart"/> Add to Cart`
- **Element text before children** — `<h4>Customer Service<i class="fa fa-chevron-right"/></h4>` → key is `Customer Service`

When in doubt, run the extractor and search `strings_map`:

```python
import gen_po
[k for k in gen_po.strings_map if 'your search term' in k]
```

### 3. Add translations to `gen_po.py`

Open `gen_po.py` and find the `TRANSLATIONS` dict (starts around line 128). It is structured as:

```python
TRANSLATIONS = {
    'zh_CN': {
        'English source': 'Chinese translation',
        ...
    },
    'fr': { ... },
    'de': { ... },
    'it': { ... },
    'ja': { ... },
    'pt': { ... },
    'es': { ... },
}
```

**Rule: the key is always the plain English text — never the XML fragment.**

The `translate_fragment()` function handles building the XML msgstr automatically. You only supply the text part.

#### Example — adding a new plain string

New button in the template: `<button>Track Order</button>`

Add to each language dict:

```python
'zh_CN': {
    ...
    'Track Order': '跟踪订单',
},
'fr': {
    ...
    'Track Order': 'Suivre la commande',
},
# repeat for de, it, ja, pt, es
```

#### Example — adding a mixed-content string

New link: `<a><i class="fa fa-bell"/> Notifications</a>`

The msgid Odoo uses is `<i class="fa fa-bell"/> Notifications`. The key in `TRANSLATIONS` is still the **plain text part**: `Notifications`.

```python
'zh_CN': {
    ...
    'Notifications': '通知',
},
```

The `translate_fragment()` function will produce:
```
msgstr "<i class=\"fa fa-bell\"/> 通知"
```
automatically.

#### Example — element text before a child icon

Footer heading: `<h4>Customer Service<i class="fa fa-chevron-right"/></h4>`

The msgid is `Customer Service` (the `el.text` before the `<i>`). Key = `Customer Service`.

```python
'zh_CN': {
    ...
    'Customer Service': '客户服务',
},
```

### 4. Regenerate all `.po` files

```
python gen_po.py
```

Verify coverage increased. Inspect a `.po` file to confirm the entry looks right:

```
#. module: aveenix_website
#: model_terms:ir.ui.view,arch_db:aveenix_website.aveenix_header
msgid "<i class=\"fa fa-user-circle\"/> My Account"
msgstr "<i class=\"fa fa-user-circle\"/> 我的账户"
```

### 5. Apply to Odoo

```
python odoo-bin -u aveenix_website -d <your_database_name>
```

Then reload the website with the desired language active. If strings still show in English, check:
- Translation was loaded: Settings → Translations → check the language has entries
- Correct template xmlid: the `#: model_terms:` line must match the `id` attribute of the `<template>` in XML

---

## Troubleshooting

### "NoneType object has no attribute 'groups'" on module update

**Cause:** A `.po` or `.pot` file has entries without `#. module:` comments.  
**Fix:** Delete `i18n/aveenix_website.pot` if it exists. Regenerate all `.po` files with `gen_po.py`.

### Translations load but some strings still show English

**Cause:** The msgid in the `.po` file doesn't exactly match what Odoo extracts from `arch_db`.  
**Diagnosis:** Export translations from Odoo UI: Settings → Translations → Export Translation → select language + `aveenix_website`. Compare the exported msgids with those in your `.po`.  
**Fix:** Update `TRANSLATIONS` dict to include the correct plain-text key, then regenerate.

### String is inside a `t-if` / `t-foreach` block and not translating

**Cause:** Elements with `t-` directives are skipped by Odoo's translator. Move the translatable text outside the directive, or wrap it in a child element without directives.

### New XML view file added

If a new `.xml` view file is added to the module, register it in `gen_po.py`:

```python
for fname in ['templates.xml', 'layout.xml', 'your_new_file.xml']:  # add here
```

---

## Adding a new language

1. Add the language code and plural forms to `LANG_META` in `gen_po.py`:

```python
LANG_META = {
    ...
    'ko': ('Korean', 'nplurals=1; plural=0;'),
}
```

2. Add a translation dict to `TRANSLATIONS`:

```python
TRANSLATIONS = {
    ...
    'ko': {
        'Shop Now': '지금 구매',
        'Add to Cart': '장바구니에 추가',
        # ... all strings
    },
}
```

3. Run `python gen_po.py` — this creates `i18n/ko.po`.

4. Install the Korean language in Odoo: Settings → Translations → Activate a Language.

5. Update the module: `python odoo-bin -u aveenix_website -d <db>`.

---

## How `gen_po.py` works (for agents)

```
gen_po.py
├── XML parsing (lxml)
│   ├── Parses templates.xml and layout.xml
│   ├── process_node() — mimics Odoo's translate_xml_node algorithm
│   │   ├── Groups consecutive translatable inline children into fragments
│   │   ├── Calls add_string(fragment, xmlid) for each translatable unit
│   │   └── Recurses into non-translatable (directive) elements
│   └── strings_map: { msgid → set of xmlids }
│
├── TRANSLATIONS dict
│   └── { lang_code → { english_plain_text → translated_plain_text } }
│
├── translate_fragment(msgid, translations)
│   ├── If msgid has no XML tags: direct dict lookup
│   ├── If msgid is XML fragment: parse → walk nodes → replace text/tail → re-serialize
│   └── Returns translated msgstr or '' if nothing matched
│
└── write_po(lang, ...)
    ├── Writes PO header
    ├── For each (msgid, xmlids): calls translate_fragment → writes entry
    └── Saves to i18n/<lang>.po
```

### Critical invariant

The keys in `TRANSLATIONS[lang]` are **always plain English text strings** — never XML fragments. `translate_fragment()` handles the XML wrapping automatically by walking the fragment tree and replacing matching text nodes.

This means: if `"Add to Cart"` appears in 6 different XML fragments across the codebase, you add it **once** to the dict and all 6 fragments get translated.

---

## Quick reference — translation dict key rules

| Template source | Odoo msgid | Key in TRANSLATIONS dict |
|---|---|---|
| `<span>Shop Now</span>` | `Shop Now` | `Shop Now` |
| `<a><i class="fa fa-cart"/> Add to Cart</a>` | `<i class="fa fa-cart"/> Add to Cart` | `Add to Cart` |
| `<h4>Customer Service<i class="fa fa-chevron-right"/></h4>` | `Customer Service` | `Customer Service` |
| `<h1>Summer Electronics<br/>Sale</h1>` | `Summer Electronics` + `Sale` (two entries) | `Summer Electronics` and `Sale` |
| `<input placeholder="Search..."/>` | `Search...` (attribute) | `Search...` |
| `<button t-if="x">Buy</button>` | NOT extracted (has t- directive) | — |
