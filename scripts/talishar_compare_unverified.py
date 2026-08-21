"""Build a side-by-side Talishar / our-JSON comparison for a chosen population.

Talishar is a SECOND OPINION, not ground truth — its own README says it may have
bugs. A divergence flags a card for review; it does not prove we are wrong.
"""
import json
import os
import re
import sys

sys.path.insert(0, 'scripts')
import talishar_reference as T

OUT = (r'C:\Users\Joseph\AppData\Local\Temp\claude'
       r'\C--Users-Joseph-Desktop-FAB-Sim'
       r'\c339b84d-4760-4cca-90e9-ac944ff4455c\scratchpad')


def load_cards():
    cards = {}
    for r, _, fs in os.walk('engine/card_effects/json'):
        if (any(p.startswith('.') for p in r.split(os.sep))
                or 'needs_review' in r or 'batch' in r):
            continue
        for f in fs:
            if f.endswith('.json') and not f.endswith('_work_queue.json'):
                cards[f[:-5]] = json.load(open(os.path.join(r, f), encoding='utf-8'))
    return cards


def main():
    idx = T.build_slug_index()
    cardidx = json.load(open('card_data/slug_index.json', encoding='utf-8'))['by_slug']
    cards = load_cards()

    test_text = ''
    for r, _, fs in os.walk('tests'):
        for f in fs:
            if f.endswith('.py'):
                test_text += open(os.path.join(r, f), encoding='utf-8',
                                  errors='ignore').read()
    named = {s for s in cards if s in test_text}
    commented = {s for s, d in cards.items() if (d.get('_comment') or '').strip()}

    def complexity(s):
        t = (cardidx.get(s) or {}).get('functionalText') or ''
        t = re.sub(r'\*\*[^*]+\*\*', '', t)
        return len([x for x in re.split(r'[.\n]', t) if x.strip()])

    unver = set(cards) - named - commented
    targets = sorted(s for s in unver if complexity(s) >= 3 and s in idx)

    lines = [f'# Talishar cross-check: {len(targets)} complex, unverified cards', '']
    for s in targets:
        text = (cardidx.get(s) or {}).get('functionalText') or ''
        lines.append(f'## {s}')
        lines.append(f'TEXT: {text.strip()}')
        lines.append(f'OURS: {json.dumps(cards[s].get("abilities", []))}')
        blocks = idx.get(s, [])
        for b in blocks:
            code = (b.get('code') or '').strip()
            if code:
                lines.append(f'TALISHAR {b["func"]}(): {code[:900]}')
        lines.append('')
    path = os.path.join(OUT, 'tal_compare.md')
    open(path, 'w', encoding='utf-8').write('\n'.join(lines))
    print('wrote', path, 'for', len(targets), 'cards')
    json.dump(targets, open(os.path.join(OUT, 'risk_slugs.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
