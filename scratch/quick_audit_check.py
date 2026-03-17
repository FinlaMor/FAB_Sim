import sqlite3
import json

conn = sqlite3.connect('data_collection/embedder_middleman_seed42/seeded_model_like_replay.db')

print('=== COMBAT STEPS CHECK ===')
combat = conn.execute('''
    SELECT step_idx, phase, obs_json
    FROM transitions
    WHERE obs_json LIKE '%"step":"combat_%'
    ORDER BY step_idx
    LIMIT 30
''').fetchall()

print(f'Found {len(combat)} combat transitions (step="combat_*")')
for idx, phase, obs_str in combat[:15]:
    obs = json.loads(obs_str)
    step = obs.get('step')
    combat_active = obs.get('combat_active')
    print(f'{idx:4d} | phase={phase:20s} | step={step:25s} | combat_active={combat_active}')

print('\n=== ACTION STRUCTURE - CHECKING SELECTED_ACTION ===')
actions_with_costs = conn.execute('''
    SELECT step_idx, action_json
    FROM transitions
    WHERE action_json LIKE '%action_cost%'
    ORDER BY step_idx
    LIMIT 5
''').fetchall()

for idx, act_str in actions_with_costs:
    act = json.loads(act_str)
    sel_act = act.get('selected_action', {})
    print(f'\nstep_idx={idx}:')
    print(f'  type: {sel_act.get("type")}')
    print(f'  action_cost: {sel_act.get("action_cost")}')
    print(f'  resource_cost: {sel_act.get("resource_cost")}')
    print(f'  has_go_again: {sel_act.get("has_go_again")}')
    print(f'  meld_side: {sel_act.get("meld_side")}')

print('\n=== GO AGAIN CHECK ===')
go_again_actions = conn.execute('''
    SELECT step_idx, action_json
    FROM transitions
    WHERE action_json LIKE '%has_go_again%true%'
    ORDER BY step_idx
    LIMIT 10
''').fetchall()

print(f'Found {len(go_again_actions)} go_again actions')
for idx, act_str in go_again_actions:
    act = json.loads(act_str)
    sel_act = act.get('selected_action', {})
    card = sel_act.get('card', {})
    print(f'  step={idx:4d}: type={sel_act.get("type"):15s} card={card.get("slug", "?")}')

print('\n=== MELD SIDE CHECK ===')
meld_actions = conn.execute('''
    SELECT step_idx, action_json
    FROM transitions
    WHERE action_json LIKE '%meld_side%'
      AND action_json NOT LIKE '%meld_side":null%'
    ORDER BY step_idx
    LIMIT 20
''').fetchall()

print(f'Found {len(meld_actions)} meld actions')
for idx, act_str in meld_actions:
    act = json.loads(act_str)
    sel_act = act.get('selected_action', {})
    card = sel_act.get('card', {})
    meld_side = sel_act.get('meld_side')
    meld_str = str(meld_side) if meld_side is not None else 'None'
    card_slug = card.get("slug", "?") if card else "?"
    print(f'  step={idx:4d}: meld_side={meld_str:6s} card={card_slug}')

conn.close()
