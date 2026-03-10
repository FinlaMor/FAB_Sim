"""Test that actual Card.get() uses the fixed targeting patterns."""

from engine.card import Card
import json

# Load a few cards to test the actual implementation
test_cards_data = [
    {
        "slug": "runechant_token",
        "name": "Runechant",
        "text": "When you play an attack action card or attack with a weapon, destroy Runechant and deal 1 arcane damage to target opposing hero."
    },
    {
        "slug": "lunging_press_red",
        "name": "Lunging Press",
        "text": "Target attack action card gets +1{p}."
    },
    {
        "slug": "dramatic_pause",
        "name": "Dramatic Pause",
        "text": "When this enters the arena, target defending action card gets +3{d} this chain link."
    },
    {
        "slug": "cintari_boost",
        "name": "Cintari Sellsword Boost",
        "text": "Target sword attack gets go again and \"When this hits, create a Cintari Sellsword token.\""
    },
    {
        "slug": "quicken_token",
        "name": "Quicken",
        "text": "When this defends an attack with go again, {t} target hero or ally."
    },
]

print("=" * 80)
print("VERIFYING ACTUAL Card.get() IMPLEMENTATION")
print("=" * 80)
print()

for card_data in test_cards_data:
    # Manually construct a card to test the parsing
    raw = {
        "name": card_data["name"],
        "text": card_data["text"],
        "types": ["Action"],
    }
    
    # Call Card.get() to parse the card (this uses the actual implementation)
    try:
        card = Card.get(card_data["slug"], raw)
        
        print(f"{card.name}:")
        print(f"  Text: {card_data['text'][:70]}...")
        print(f"  requires_target: {card.requires_target}")
        print(f"  can_target_hero: {card.can_target_hero}")
        print(f"  can_target_attack: {card.can_target_attack}")
        print(f"  can_target_permanent: {card.can_target_permanent}")
        print()
        
    except Exception as e:
        print(f"{card_data['name']}: ERROR - {e}")
        print()

print("=" * 80)
print("If all flags are detected correctly, the implementation is working.")
print("=" * 80)
