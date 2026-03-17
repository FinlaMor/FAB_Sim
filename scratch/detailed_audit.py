"""
Detailed audit of combat structure and meld mechanics using JSONL log
"""
import json
from collections import Counter

# Load all decisions
decisions = []
with open('data_collection/embedder_middleman_seed42/embedder_tap_decisions.jsonl', 'r') as f:
    for line in f:
        decisions.append(json.loads(line))

print("="*80)
print("DETAILED FAB RULES AUDIT - JSONL DATA")
print("="*80)

# 1. Combat Chain Structure Audit (CR 7)
print("\n[1] COMBAT CHAIN STRUCTURE (CR 7)")
print("-"*80)

combat_decisions = [d for d in decisions if 'combat' in d.get('step', '')]
print(f"Total combat step decisions: {len(combat_decisions)}")

# Get step sequence for first combat chain
first_combat_chain = []
for i, d in enumerate(decisions):
    if 'combat' in d.get('step', ''):
        # Get this combat chain (consecutive combat steps)
        if not first_combat_chain:
            first_combat_chain.append((i, d))
        elif first_combat_chain and len(first_combat_chain) < 20:
            first_combat_chain.append((i, d))
        else:
            break

print("\nFirst combat chain structure:")
print("  Line | Turn | Step                | Combat_active | Player_action")
for i, d in first_combat_chain:
    step = d.get('step', '?')
    turn = d.get('turn', '?')
    state = d.get('state_input', {})
    combat_active = state.get('combat_active', '?')
    action = d.get('chosen_action', {})
    action_type = action.get('type', '?')
    print(f"  {i:4d} | {turn:4} | {step:19s} | {combat_active!s:13s} | {action_type}")

# CR 7 expected sequence: layer, attack, defend, reaction, damage, resolution, close
cr7_expected = ['combat_layer', 'combat_attack', 'combat_defend', 'combat_reaction', 
                'combat_damage', 'combat_resolution', 'combat_chain_close']

combat_steps_found = Counter([d.get('step') for d in combat_decisions])
print("\nCombat step distribution:")
for step in cr7_expected:
    count = combat_steps_found.get(step, 0)
    print(f"  {step:25s}: {count:3d} occurrences")

# Check if combat_chain_close exists
close_decisions = [d for d in decisions if d.get('step') == 'combat_chain_close']
print(f"\nCombat chain close steps: {len(close_decisions)}")
if close_decisions:
    print("  CR 7.7.1: Players do NOT get priority during Close Step")
    print("  Checking - should see 0 player decisions during close:")
    for i, d in enumerate(decision for decision in decisions if decision.get('step') == 'combat_chain_close'):
        if i < 5:
            turn = d.get('turn')
            action = d.get('chosen_action', {})
            action_type = action.get('type')
            print(f"    Turn {turn}: action_type={action_type}")

# Check combat_active flag during combat steps
print("\nCombat_active flag verification:")
combat_active_violations = []
for d in combat_decisions:
    state = d.get('state_input', {})
    combat_active = state.get('combat_active')
    step = d.get('step')
    if not combat_active:
        combat_active_violations.append((d.get('turn'), step))

if combat_active_violations:
    print(f"  ❌ {len(combat_active_violations)} combat steps have combat_active=False")
    print("    First 5 violations:")
    for turn, step in combat_active_violations[:5]:
        print(f"      Turn {turn}, step={step}")
else:
    print(f"  ✓ All {len(combat_decisions)} combat steps have combat_active=True")

# 2. Meld Card Dual-Resolution Audit
print("\n[2] MELD CARD DUAL-RESOLUTION (meld_side='both')")
print("-"*80)

meld_decisions = [(i, d) for i, d in enumerate(decisions) 
                  if d.get('chosen_action', {}).get('meld_side') not in [None, 'None']]
print(f"Total meld plays: {len(meld_decisions)}")

meld_sides = Counter([d.get('chosen_action', {}).get('meld_side') for _, d in meld_decisions])
print("\nMeld side distribution:")
for side, count in sorted(meld_sides.items()):
    print(f"  {side:6s}: {count:2d} plays")

# Find 'both' meld plays
both_melds = [(i, d) for i, d in meld_decisions 
              if d.get('chosen_action', {}).get('meld_side') == 'both']
print(f"\nMeld 'both' plays (should show dual resolution with priority gap):")
print(f"Found {len(both_melds)} 'both' meld plays")

for idx, (line_num, d) in enumerate(both_melds):
    if idx >= 2:  # Show first 2 'both' melds
        break
    
    turn = d.get('turn')
    card = d.get('chosen_action', {}).get('card', {})
    card_slug = card.get('slug', '?') if card else '?'
    
    print(f"\n  'Both' meld #{idx+1}: line {line_num}, turn {turn}, card={card_slug}")
    print("    Checking next 15 steps for dual resolution:")
    print("      Line | Step                | Action_type        | Stack | Chain")
    
    for offset in range(15):
        if line_num + offset < len(decisions):
            next_d = decisions[line_num + offset]
            next_step = next_d.get('step', '?')
            next_state = next_d.get('state_input', {})
            next_action = next_d.get('chosen_action', {})
            next_type = next_action.get('type', '?')
            stack_size = next_state.get('stack_size', 0)
            chain_len = next_state.get('chain_length', 0)
            print(f"      {line_num+offset:4d} | {next_step:19s} | {next_type:18s} | {stack_size:3d}   | {chain_len}")

# 3. Action Point Economy
print("\n[3] ACTION POINT ECONOMY (CR 4.3.2)")
print("-"*80)

# CR 4.3.2: Turn-player gets 1 AP at start of action phase
print("CR 4.3.2: Turn-player gets 1 action point at action phase start")
print("Checking: First action phase decision of each turn should show AP available")

turns_checked = set()
print("\n  Turn | Player | Step   | Type                | Result")
for i, d in enumerate(decisions):
    turn = d.get('turn')
    step = d.get('step')
    if step == 'action' and turn not in turns_checked:
        turns_checked.add(turn)
        player = d.get('state_input', {}).get('active_player')
        action = d.get('chosen_action', {})
        action_type = action.get('type', '?')
        
        # Since action_cost fields are None, check if certain action types were chosen
        # that require AP (play_card, attack_weapon, etc.)
        ap_consuming = action_type in ['play_card', 'attack_weapon', 'activate_weapon', 'activate_hero']
        result = "AP consumed" if ap_consuming else "No AP action"
        
        print(f"  {turn:4d} | P{player}     | {step:6s} | {action_type:19s} | {result}")
        if len(turns_checked) >= 15:
            break

# 4. Priority Management
print("\n[4] PRIORITY MANAGEMENT (CR 1.11)")
print("-"*80)

# Check end_phase_beginning for priority
end_phase_decisions = [d for d in decisions if d.get('step') == 'end_phase_beginning']
print(f"End phase decisions: {len(end_phase_decisions)}")

# CR 4.4.1: Players do not get priority during End Phase UNLESS triggered layers exist
# Count how many end phase decisions involve passes vs other actions
end_phase_actions = Counter([d.get('chosen_action', {}).get('type') for d in end_phase_decisions])
print("\nEnd phase action types:")
for action_type, count in sorted(end_phase_actions.items()):
    print(f"  {action_type if action_type else 'None':20s}: {count:3d}")

# 5. Summary
print("\n[5] GAME SUMMARY")
print("-"*80)
final = decisions[-1]
final_state = final.get('state_input', {})
print(f"Total decisions: {len(decisions)}")
print(f"Final turn: {final.get('turn')}")
print(f"Final health: P1={final_state.get('p1_health')}, P2={final_state.get('p2_health')}")
print(f"Winner: P{'2' if final_state.get('p1_health', 36) < final_state.get('p2_health', 40) else '1'}")

print("\n" + "="*80)
print("AUDIT COMPLETE")
print("="*80)
