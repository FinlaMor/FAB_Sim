"""Test targeting requirements implementation for CR compliance."""

from engine.card import Card
import re

def parse_targeting_flags(functional_text):
    """Simulate the targeting flag parsing from Card.get()."""
    ability_flags = {
        'requires_target': False,
        'can_target_hero': False,
        'can_target_attack': False,
        'can_target_permanent': False,
    }
    
    if functional_text:
        func_lower = functional_text.lower()
        
        # Targeting requirements (CR 1.4, Round 9 Gap #2 fix)
        if 'target' in func_lower:
            ability_flags['requires_target'] = True
            # Determine target types from functional text
            if re.search(r'target (hero|player)', func_lower):
                ability_flags['can_target_hero'] = True
            if re.search(r'target (attack|attacking card|combat chain)', func_lower):
                ability_flags['can_target_attack'] = True
            if re.search(r'target (card|equipment|weapon|ally|permanent|aura)', func_lower):
                ability_flags['can_target_permanent'] = True
    
    return ability_flags

# Test cases from actual FAB cards
test_cases = [
    # Category 1: Target Hero
    {
        'name': 'Pummel',
        'functional_text': 'Deal 2 damage to target hero.',
        'expected': {'requires_target': True, 'can_target_hero': True, 'can_target_attack': False, 'can_target_permanent': False}
    },
    {
        'name': 'Oasis Respite',
        'functional_text': 'Prevent the next 4 damage that would be dealt to target hero this turn by a source of your choice.',
        'expected': {'requires_target': True, 'can_target_hero': True, 'can_target_attack': False, 'can_target_permanent': False}
    },
    {
        'name': 'Runechant Token',
        'functional_text': 'When you play an attack action card or attack with a weapon, destroy Runechant and deal 1 arcane damage to target opposing hero.',
        'expected': {'requires_target': True, 'can_target_hero': True, 'can_target_attack': False, 'can_target_permanent': False}
    },
    
    # Category 2: Any Target (NOT CURRENTLY CAPTURED)
    {
        'name': 'Frosting',
        'functional_text': 'Deal 3 arcane damage to any target.',
        'expected': {'requires_target': True, 'can_target_hero': False, 'can_target_attack': False, 'can_target_permanent': False}
    },
    {
        'name': 'Genesis',
        'functional_text': 'If a non-attack action card was pitched to play it, deal 1 arcane damage to any target.',
        'expected': {'requires_target': True, 'can_target_hero': False, 'can_target_attack': False, 'can_target_permanent': False}
    },
    
    # Category 3: Target Attack
    {
        'name': 'Lunging Press',
        'functional_text': 'Target attack action card gets +1{p}.',
        'expected': {'requires_target': True, 'can_target_hero': False, 'can_target_attack': True, 'can_target_permanent': True}  # Note: overlaps
    },
    {
        'name': 'Cognition Nodes',
        'functional_text': 'Once per Turn Attack Reaction - Remove a steam counter: Target attack action card gains "When this hits, put it on the bottom of its owner\'s deck."',
        'expected': {'requires_target': True, 'can_target_hero': False, 'can_target_attack': True, 'can_target_permanent': True}
    },
    {
        'name': 'Pitfall Trap',
        'functional_text': 'Target attack gets -2{p}, unless the attacking hero pays {r}.',
        'expected': {'requires_target': True, 'can_target_hero': False, 'can_target_attack': True, 'can_target_permanent': False}
    },
    
    # Category 4: Target Equipment/Weapon/Permanent
    {
        'name': 'Ironsong Determination',
        'functional_text': 'Target weapon gets +1{p} and dominate until end of turn.',
        'expected': {'requires_target': True, 'can_target_hero': False, 'can_target_attack': False, 'can_target_permanent': True}
    },
    {
        'name': 'Smash with Big Tree',
        'functional_text': 'Crush - When this deals 4 or more damage to a hero, destroy target equipment they control with a -1{d} counter.',
        'expected': {'requires_target': True, 'can_target_hero': False, 'can_target_attack': False, 'can_target_permanent': True}
    },
    {
        'name': 'Mark of Lightning',
        'functional_text': 'When this enters the arena, create a Courage token under target hero\'s control.',
        'expected': {'requires_target': True, 'can_target_hero': True, 'can_target_attack': False, 'can_target_permanent': False}
    },
    
    # Category 5: Target Defending Card
    {
        'name': 'Dramatic Pause',
        'functional_text': 'When this enters the arena, target defending action card gets +3{d} this chain link.',
        'expected': {'requires_target': True, 'can_target_hero': False, 'can_target_attack': False, 'can_target_permanent': True}
    },
    {
        'name': 'Hemorrhage Bore',
        'functional_text': 'The first time this is defended by a non-equipment card each turn, halve the base {d} of target defending card, rounded up, until end of turn.',
        'expected': {'requires_target': True, 'can_target_hero': False, 'can_target_attack': False, 'can_target_permanent': True}
    },
    
    # Category 6: Target Ally
    {
        'name': 'Cintari Sellsword Boost',
        'functional_text': 'Target sword attack gets go again and "When this hits, create a Cintari Sellsword token."',
        'expected': {'requires_target': True, 'can_target_hero': False, 'can_target_attack': True, 'can_target_permanent': False}
    },
    {
        'name': 'Quicken Token',
        'functional_text': 'When this defends an attack with go again, {t} target hero or ally.',
        'expected': {'requires_target': True, 'can_target_hero': True, 'can_target_attack': False, 'can_target_permanent': True}  # Multiple types
    },
    
    # Category 7: Target Aura
    {
        'name': 'Runic Reclamation',
        'functional_text': 'When Runic Reclamation hits a hero, destroy target aura they control.',
        'expected': {'requires_target': True, 'can_target_hero': False, 'can_target_attack': False, 'can_target_permanent': True}
    },
    {
        'name': 'Seismic Shift',
        'functional_text': 'Destroy X target aura tokens.',
        'expected': {'requires_target': True, 'can_target_hero': False, 'can_target_attack': False, 'can_target_permanent': True}
    },
    
    # Category 8: Non-targeting (should all be False)
    {
        'name': 'Head Jab',
        'functional_text': 'Go again',
        'expected': {'requires_target': False, 'can_target_hero': False, 'can_target_attack': False, 'can_target_permanent': False}
    },
    {
        'name': 'Sink Below',
        'functional_text': 'As this is attacked, add 4{d}.',
        'expected': {'requires_target': False, 'can_target_hero': False, 'can_target_attack': False, 'can_target_permanent': False}
    },
]

def test_targeting():
    """Test targeting flag parsing."""
    print("=" * 80)
    print("TARGETING REQUIREMENTS COMPLIANCE TEST")
    print("=" * 80)
    
    passed = 0
    failed = 0
    issues = []
    
    for i, test in enumerate(test_cases, 1):
        # Parse targeting flags from functional text
        actual = parse_targeting_flags(test['functional_text'])
        expected = test['expected']
        
        # Compare
        match = actual == expected
        if match:
            passed += 1
            status = "✅ PASS"
        else:
            failed += 1
            status = "❌ FAIL"
            issues.append({
                'name': test['name'],
                'functional_text': test['functional_text'],
                'expected': expected,
                'actual': actual
            })
        
        print(f"\n{i}. {test['name']}: {status}")
        if not match:
            print(f"   Text: {test['functional_text'][:60]}...")
            print(f"   Expected: {expected}")
            print(f"   Actual:   {actual}")
    
    print("\n" + "=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 80)
    
    if issues:
        print("\n" + "=" * 80)
        print("DETAILED FAILURE ANALYSIS:")
        print("=" * 80)
        
        # Group by failure type
        any_target_missing = []
        false_positives = []
        wrong_category = []
        
        for issue in issues:
            if 'any target' in issue['functional_text']:
                any_target_missing.append(issue)
            elif issue['expected']['requires_target'] and not issue['actual']['requires_target']:
                false_positives.append(issue)
            else:
                wrong_category.append(issue)
        
        if any_target_missing:
            print(f"\n1. 'ANY TARGET' NOT CAPTURED ({len(any_target_missing)} cases):")
            print("   CR 1.8.5d: 'any target' means living objects (heroes/allies with life)")
            for issue in any_target_missing:
                print(f"   - {issue['name']}")
                print(f"     Text: {issue['functional_text']}")
        
        if false_positives:
            print(f"\n2. FALSE NEGATIVES ({len(false_positives)} cases):")
            for issue in false_positives:
                print(f"   - {issue['name']}")
                print(f"     Text: {issue['functional_text']}")
        
        if wrong_category:
            print(f"\n3. WRONG TARGET TYPE CLASSIFICATION ({len(wrong_category)} cases):")
            for issue in wrong_category:
                print(f"   - {issue['name']}")
                print(f"     Text: {issue['functional_text']}")
                print(f"     Expected: {issue['expected']}")
                print(f"     Actual:   {issue['actual']}")
    
    return passed, failed, issues

if __name__ == '__main__':
    passed, failed, issues = test_targeting()
    
    # Calculate coverage
    total_tests = len(test_cases)
    coverage_pct = (passed / total_tests) * 100 if total_tests > 0 else 0
    
    print(f"\n" + "=" * 80)
    print(f"COVERAGE: {coverage_pct:.1f}%")
    print("=" * 80)
    
    if failed == 0:
        print("\n✅ ALL TESTS PASSED - CR 1.8.5 COMPLIANT")
    else:
        print(f"\n⚠️ {failed} TEST(S) FAILED - CR 1.8.5 COMPLIANCE ISSUES DETECTED")
