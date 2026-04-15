Create tests/test_card_implementations.py with a consistent structure per card:

```
  # tests/test_card_implementations.py

  from engine.card import Card
  from engine.card_effects.registry import EQUIPMENT_ACTIVATION_CONDITIONS,
  EQUIPMENT_ACTIVATION_EFFECTS
  from engine.state import GameState, Player, Step
  from tests.conftest import _make_card, _make_player, _mock_agent

  # Shared minimal state builder (same pattern as test_loader_conditions.py)
  def _make_state():
      p1 = _make_player(1)
      p2 = _make_player(2)
      return GameState(players={1: p1, 2: p2}, active_player=1,
                       player_agents={1: _mock_agent, 2: _mock_agent},
                       step=Step.ACTION, turn_number=1,
                       combat=None, done=False, winner=None)

  # ── aether_ironweave ─────────────────────────────────────────────────────────

  class TestAetherIronweave:
      def _equip(self, state):
          from engine.card import CardDB
          from config import SLUG_INDEX_PATH
          card = CardDB(SLUG_INDEX_PATH).get("aether_ironweave")
          card.owner = 1; card.controller = 1; card.zone = "chest"
          state.players[1].chest.add(card)
          return card

      def _played(self, state, types, subtypes):
          """Add a card to cards_played_this_turn with the given types/subtypes."""
          c = Card(slug="test", name="Test", types=types, subtypes=subtypes)
          c.owner = 1; c.controller = 1
          state.players[1].cards_played_this_turn.append(c)

      def test_condition_false_when_no_cards_played(self):
          state = _make_state()
          card = self._equip(state)
          cond = EQUIPMENT_ACTIVATION_CONDITIONS["aether_ironweave"]
          assert cond(state.players[1], "chest", card, state) is False

      def test_condition_false_when_only_attack_action_played(self):
          state = _make_state()
          card = self._equip(state)
          self._played(state, ["Action"], ["Attack"])
          cond = EQUIPMENT_ACTIVATION_CONDITIONS["aether_ironweave"]
          assert cond(state.players[1], "chest", card, state) is False

      def test_condition_false_when_only_non_attack_action_played(self):
          state = _make_state()
          card = self._equip(state)
          self._played(state, ["Action"], [])
          cond = EQUIPMENT_ACTIVATION_CONDITIONS["aether_ironweave"]
          assert cond(state.players[1], "chest", card, state) is False

      def test_condition_true_when_both_played(self):
          state = _make_state()
          card = self._equip(state)
          self._played(state, ["Action"], ["Attack"])
          self._played(state, ["Action"], [])
          cond = EQUIPMENT_ACTIVATION_CONDITIONS["aether_ironweave"]
          assert cond(state.players[1], "chest", card, state) is True

      def test_effect_grants_resources_and_go_again(self):
          state = _make_state()
          player = state.players[1]
          player.resources = 0
          player.action_points = 0
          EQUIPMENT_ACTIVATION_EFFECTS["aether_ironweave"](None, player, state)
          assert player.resources == 2
          assert player.action_points == 1
```


  Why this structure:

  - One class per card — easy to find, groups all related assertions
  - Test condition separately — covers True/False branches explicitly; catches logic errors in partial
   conditions
  - Test effect separately — call the effect function directly with a minimal state; fast and precise
  - No full engine run needed — equipment activations are immediate (no stack), so calling the
  registries directly is a faithful test
  - Reuse _make_state() — same helper pattern as the rest of the test suite

  The only thing that isn't covered by this approach is the destroy-self path (the generic engine
  fallback). If you want that tested too, you'd add a third test method that calls
  _apply_activate_equipment directly and asserts the card moved to graveyard. But that requires
  importing engine internals — worth doing for any card whose cost is non-trivial.


  The pattern is simple — replace _mock_agent (which always picks options[0]) with a scripted agent
  for the specific test:
```
  class TestAetherIcevein:

      def _make_agent(self, choices: list):
          """Returns an agent that pops from a predefined choices list in order."""
          choices = list(choices)
          def agent(state, options, **kwargs):
              return choices.pop(0) if choices else options[0]
          return agent

      def test_damage_directed_at_hero(self):
          state = _make_state()
          # Agent chooses the hero (first option) when asked where to direct damage
          state.player_agents[1] = self._make_agent([True])   # e.g. "target hero? yes"
          state.player_agents[2] = self._make_agent([True])

          player = state.players[1]
          opp = state.players[2]
          starting_health = opp.health

          _aether_icevein_effect(None, player, state)

          assert opp.health < starting_health

      def test_damage_directed_at_equipment(self):
          state = _make_state()
          # Agent chooses to hit equipment instead
          equipment = _make_equipment_card(...)
          state.players[2].chest.add(equipment)
          state.player_agents[1] = self._make_agent([False, equipment.slug])

          _aether_icevein_effect(None, state.players[1], state)

          # assert equipment took damage / was destroyed
          assert equipment not in state.players[2].chest.cards
```


  The key insight: _ask_player is just a function call through state.player_agents. You control every
  decision point by injecting a scripted agent that returns predetermined values in order. The choices
   list acts as a script — each call to the agent pops the next answer.

  For complex multi-decision effects, annotate the choices list so the test is self-documenting:

  state.player_agents[1] = self._make_agent([
      False,              # "target hero?" → no, target equipment
      "chest_armor_slug", # "which equipment?" → chest piece
  ])

  One practical tip: when an effect has an optional decision ([True, False]), write two tests — one
  with True and one with False. This covers both branches and makes it obvious what each choice means.

  The _make_agent helper is worth putting in conftest.py so all test files can use it, since most
  non-trivial cards will need it.

● The damage value is already in card.base_arcane_damage, so you write one function that reads from
  the card, and register it for all three variants:
```
  def _aether_icevein_effect(action, player, state):
      damage = action.card.base_arcane_damage  # 5 / 4 / 3 depending on color
      # ... deal damage logic using that value

  for _slug in ("aether_icevein_red", "aether_icevein_yellow", "aether_icevein_blue"):
      PLAY_ABILITIES[_slug] = _aether_icevein_effect
```

  For tests, use @pytest.mark.parametrize:
```
  @pytest.mark.parametrize("slug,expected_damage", [
      ("aether_icevein_red",    5),
      ("aether_icevein_yellow", 4),
      ("aether_icevein_blue",   3),
  ])
  def test_aether_icevein_deals_correct_damage(slug, expected_damage):
      state = _make_state()
      card = CardDB().get(slug)
      card.owner = 1; card.controller = 1
      state.player_agents[1] = _make_agent(["hero"])  # target hero

      opp = state.players[2]
      starting_health = opp.health

      PLAY_ABILITIES[slug](MockAction(card), state.players[1], state)

      assert opp.health == starting_health - expected_damage
```

  This is the general rule: if the only difference between variants is a numeric value that's already
  on the card object (base_power, base_arcane_damage, base_cost, etc.), write one function reading
  from the card and parametrize the test. You only need separate implementations when the variants
  have genuinely different logic, not just different numbers.
