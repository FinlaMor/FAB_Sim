import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from engine.card import CardDB

def test_multi_ability_detection():
    db = CardDB()
    
    print("=" * 70)
    print("MULTI-ABILITY DECOMPOSITION TEST")
    print("=" * 70)
    print()
    
    test_cards = [
        ("cracked_bauble", "Cracked Bauble", "Activated + Triggered", 2),
        ("bone_basher", "Bone Basher", "Activated only", 1),
        ("tunic", "Tunic", "Static only", 1),
    ]
    
    passed = 0
    failed = 0
    
    for slug, name, description, expected_count in test_cards:
        print(f"Test: {name}")
        print(f"  Slug: {slug}")
        print(f"  Expected ability_type_count: {expected_count}")
        
        card = db.get(slug)
        if card is None:
            print(f"  CARD NOT FOUND")
            continue
        
        print(f"  has_activated_ability: {card.has_activated_ability}")
        print(f"  has_triggered_ability: {card.has_triggered_ability}")
        print(f"  has_static_ability: {card.has_static_ability}")
        print(f"  ability_type_count: {card.ability_type_count}")
        print(f"  has_multiple_ability_types: {card.has_multiple_ability_types}")
        
        if card.ability_type_count == expected_count:
            print(f"  PASS")
            passed += 1
        else:
            print(f"  FAIL - Expected {expected_count}, got {card.ability_type_count}")
            failed += 1
        print()
    
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

if __name__ == "__main__":
    test_multi_ability_detection()
