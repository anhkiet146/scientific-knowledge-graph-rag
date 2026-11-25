"""Exclude visibly corrupt PDF text lines without inventing repaired mathematics.

Original prepared JSON/PDF stays unchanged. Contiguous clean fragments remain
separate evidence sections so quotes cannot bridge a removed line.
"""
import hashlib


def split_page(text):
    lines = text.split('\n')
    excluded = [i for i, line in enumerate(lines) if '\ufffd' in line]
    if not excluded:
        return [{'text': text, 'first_line': 1, 'last_line': len(lines)}], []
    fragments, rejected = [], []
    start = 0
    for index in excluded + [len(lines)]:
        if index > start:
            block = '\n'.join(lines[start:index])
            if block.strip():
                fragments.append({'text': block, 'first_line': start + 1, 'last_line': index})
        if index < len(lines):
            rejected.append({'line_number': index + 1,
                             'reason': 'unicode_replacement_character',
                             'sha256': hashlib.sha256(lines[index].encode()).hexdigest(),
                             'replacement_characters': lines[index].count('\ufffd')})
        start = index + 1
    return fragments, rejected


def quality_report(document):
    pages = []
    for section in document.get('sections', []):
        if section.get('category') != 'pdf_page':
            continue
        fragments, rejected = split_page(section.get('content', ''))
        if rejected:
            pages.append({'page': section.get('page'), 'title': section.get('section_title'),
                          'excluded_lines': rejected, 'retained_fragments': len(fragments),
                          'retained_characters': sum(len(f['text']) for f in fragments)})
    return {'policy': 'exclude U+FFFD-bearing physical lines; no inferred replacements',
            'original_source_changed': False, 'affected_pages': len(pages),
            'excluded_lines': sum(len(p['excluded_lines']) for p in pages), 'pages': pages,
            'semantic_correctness': 'not_established',
            'limits': 'Clean fragments may still contain parsing errors. Unreadable equations, image-only data and removed co-column content are not recovered.'}
