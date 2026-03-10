"""Test to verify multi-ability decomposition implementation.

This test validates whether the multi-ability decomposition features are working:
1. ability_type_count: Count of distinct ability types (0-3)
2. has_multiple_ability_types: True if count >= 2

Expected behavior:
- Cards with activated + triggered abilities should have count=2
- Cards with activated + triggered + static should have count=3
- Cards with only one ability type should have count=1
"""

import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from engine.card import CardDB

def test_multi_ability_detection():
    """Test cards known to have multiple ability types."""
    db = CardDB()
    
    print("=" * 70)
    print("MULTI-ABILITY DECOMPOSITION TEST")
    print("=" * 70)
    print()
    
    # Test cases: cards with multiple known ability types
    test_cards = [
        # Cards with activated + triggered abilities
        ("cracked_bauble", "Cracked Bauble", 
         "Activated (Action - {r}) + Triggered (ETB)", 2),
        
        # Cards with activated abilities only
        ("bone_basher", "Bone Basher", 
         "Activated only (Action - {r}{r}: Attack)", 1),
        
        # Cards with triggered abilities only
        ("genesis_aetherus", "Genesis, Aetherus", 
         "Triggered only (ETB)", 1),
        
        # Cards with static abilities only
        ("tunic", "Tunic", 
         "Static only (continuous +1{h})", 1),
    ]
    
    passed = 0
    failed = 0
    missing_cards = 0
    
    for slug, name, description, expected_count in test_cards:
        print(f"\nTest: {name}")
        print(f"  Slug: {slug}")
        print(f"  Description: {description}")
        print(f"  Expected ability_type_count: {expected_count}")
        
        card = db.get(slug)
        if card is None:
            print(f"  ❌ CARD NOT FOUND")
            missing_cards += 1
            continue
        
        # Check ability flags
        print(f"  has_activated_ability: {card.has_activated_ability}")
        print(f"  has_triggered_ability: {card.has_triggered_ability}")
        print(f"  has_static_ability: {card.has_static_ability}")
        print(f"  ability_type_count: {card.ability_type_count}")
        print(f"  has_multiple_ability_types: {card.has_multiple_ability_types}")
        
        # Verify calculation
        actual_count = card.ability_type_count
        expected_multiple = expected_count >= 2
        actual_multiple = card.has_multiple_ability_types
        
        if actual_count == expected_count and actual_multiple == expected_multiple:
            print(f"  ✅ PASS")
            passed += 1
        else:
            print(f"  ❌ FAIL - Expected count={expected_count}, got {actual_count}")
            print(f"          Expected has_multiple={expected_multiple}, got {actual_multiple}")
            failed += 1
    
    print()
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed, {missing_cards} missing")
    print("=" * 70)
    
    if failed > 0:
        print("\n⚠️  MULTI-ABILITY DECOMPOSITION NOT WORKING")
        print("The ability_type_count calculation logic is missing from engine/card.py")
        print("\nExpected logic (should be in CardDB.get() after ability_flags parsing):")
        print("""
ability_type_count = 0
if ability_flags['has_activated_ability']:
    ability_type_count += 1
if ability_flags['has_triggered_ability']:
    ability_type_count += 1
if ability_flags['has_static_ability']:
    ability_type_count += 1
ability_flags['ability_type_count'] = ability_type_count
ability_flags['has_multiple_ability_types'] = ability_type_count >= 2
""")
    
    return passed, failed, missing_cards

if __name__ == "__main__":
    test_multi_ability_detection()
