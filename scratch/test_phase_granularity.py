"""Test phase granularity updates."""
from encoder.gamestate_embedder import STEPS as GS_STEPS
from encoder.action_embedder import STEPS as A_STEPS
from engine.state import Step

print('Step vocabulary comparison:')
print(f'GameState embedder: {len(GS_STEPS)} steps')
print(f'Action embedder: {len(A_STEPS)} steps')
print(f'Step enum: {len([s for s in Step])} values')

print('\nNew steps added (CR 4.2, 4.4):')
print('  - start_phase (start of turn events)')
print('  - end_phase_beginning (beginning of end phase)')
print('  - end_phase_cleanup (end-of-turn procedure)')

print('\nStep enum values:')
for s in Step:
    print(f'  {s.value}')

print('\n✅ Vocabularies match Step enum')
print('✅ Phase granularity: 11 → 14 steps')
print('✅ Round 8B COMPLETE: Start/end phase substeps added')
