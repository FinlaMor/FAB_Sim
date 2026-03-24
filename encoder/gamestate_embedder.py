"""GameState embedder for FAB AI agents.

Converts GameState objects into fixed-size neural network embeddings suitable for:
- Value network inputs (state evaluation)
- Policy network context (state-conditional action selection)
- Critic networks in RL (Q-learning, Actor-Critic)

Architecture:
GameState has two main components:
1. Player states (symmetric) - both active and inactive player
2. Global state (turn, combat, stack, chain)

Player State Features (per player):
- Health: 1-dim normalized
- Intellect: 1-dim normalized
- Resources: 1-dim normalized
- Action points: 1-dim normalized
- Flags: weapon_exhausted, hero_power_exhausted, arsenal_face_up, marked (4-dim)
- Zone sizes: hand, deck, graveyard, arsenal, banished, pitch, inventory (7-dim)
- Equipment slots: head, chest, arms, legs, weapon1, weapon2 (6 * d_model from CardEmbedder)
- Permanents zone: sum-pooled embedding of items, auras, allies, soul, tokens (1 * d_model) + count scalar
- Total per player: 28 + len(COUNTER_TYPES) + 7*d_model

Global State Features:
- Turn number: 1-dim normalized
- Active player: 1-dim binary
- Step: 12-dim one-hot (BEGIN_GAME, ACTION, COMBAT_*, END_*)
- Priority player: 1-dim binary
- Consecutive passes: 1-dim normalized
- Combat state: 13-dim + 4*d_model (attack card, attack source, defending cards, defending equipment)
    + len(CARD_KEYWORDS)-dim (keywords multi-hot)
- Stack state: 5 * (8 + d_model) explicit layers + (11 + 2*d_model) pooled/ordering summary
- Chain links: 3-dim aggregated (count, avg power, hits)
- Total global: 218 + len(CARD_KEYWORDS) + 11*d_model

Total State Embedding:
2*(28 + len(COUNTER_TYPES) + 7*d_model) + (218 + len(CARD_KEYWORDS) + 11*d_model)
With d_model=128 and current registries: 3628 dimensions

Note: legality checking is intentionally out of scope for embeddings. The engine and
legal action generator are responsible for enforcing legal play before states/actions
reach the model.
"""

import torch
import torch.nn as nn
from typing import Optional

from engine.state import GameState, Player, Step, CombatState, Zone
from encoder.card_embedder import CardEmbedder, SlugVocab, card_to_features
from encoder.feature_schema import (
    CARD_KEYWORDS,
    COUNTER_OOV_TYPE,
    COUNTER_TYPES,
    KEYWORD_OOV_TOKEN,
    STEP_VOCABULARY,
    build_schema_metadata,
    normalize_counter,
    validate_schema_metadata,
)
from engine.card import Card


_CARD_KEYWORD_IDX = {keyword.lower(): idx for idx, keyword in enumerate(CARD_KEYWORDS)}
_CARD_KEYWORD_OOV_IDX = _CARD_KEYWORD_IDX[KEYWORD_OOV_TOKEN.lower()]

STEPS = STEP_VOCABULARY

MAX_STACK_LAYERS = 5
STACK_LAYER_TYPES = ['card', 'activated', 'triggered']


class PlayerStateEmbedder(nn.Module):
    """Embeds a single Player object into fixed-size vector.
    
    Features:
    - Scalar resources: health, intellect, resources, action_points (4-dim)
    - Binary flags: weapon_exhausted, hero_power_exhausted, arsenal_face_up, marked (4-dim)
    - Zone sizes: hand, deck, graveyard, arsenal, banished, pitch, inventory (7-dim)
    - Equipment cards: head, chest, arms, legs, weapon1, weapon2 (6 * d_model)
    - Permanents zone cards: items, auras, allies, soul, tokens (1 * d_model aggregated)

    Total: (28 + len(COUNTER_TYPES)) scalar features + 7*d_model card features
    """
    
    def __init__(self, d_model: int = 128, card_embedder: Optional[CardEmbedder] = None, slug_vocab_size: int = 4563, slug_vocab: Optional[SlugVocab] = None):
        super().__init__()
        self.d_model = d_model
        self.slug_vocab = slug_vocab
        
        if card_embedder is None:
            self.card_embedder = CardEmbedder(slug_vocab_size=slug_vocab_size, d_model=d_model)
        else:
            self.card_embedder = card_embedder
        
        # Normalization constants
        self.norm_health = 50.0
        self.norm_intellect = 10.0
        self.norm_resources = 10.0
        self.norm_action_points = 5.0
        self.norm_zone_size = 30.0
        self.norm_counters = 10.0  # For counter types (steam, flow, suspense, etc.)
    
    def embed_card(self, card: Optional[Card], player_counters: Optional[dict] = None) -> torch.Tensor:
        """Helper to embed a single card using card_to_features."""
        if card is None or self.slug_vocab is None:
            return torch.zeros(self.d_model)
        
        features = card_to_features(card, self.slug_vocab, player_counters=player_counters)
        # Add batch dimension
        features = {k: v.unsqueeze(0) if v.dim() == 0 or (v.dim() == 1 and k not in ["numeric", "types", "subtypes", "supertypes", "keywords"]) else v.unsqueeze(0) 
                   for k, v in features.items()}
        emb = self.card_embedder(features)
        return emb.squeeze(0)  # Remove batch dim
    
    def get_output_dim(self) -> int:
        """Total output dimension: 28 + len(COUNTER_TYPES) + 7*d_model
        Breakdown: health(1) + intellect(1) + resources(1) + action_points(1) + 
                   weapon_exhausted(1) + hero_power_exhausted(1) + arsenal_face_up(1) + marked(1) +
                   counters(len(COUNTER_TYPES)) + zone_sizes(7) + equipment_cards(6*d_model) + equipment_exhausted(6) + 
                   equipment_tapped(6) + permanents_zone(d_model) + permanents_count(1)
        With d_model=128 and current counter registry: 967 dimensions
        """
        return 28 + len(COUNTER_TYPES) + 7 * self.d_model
    
    def forward(self, player: Player, player_counters: Optional[dict] = None) -> torch.Tensor:
        """Convert Player to embedding tensor.
        
        Args:
            player: Player object to embed
            player_counters: Optional counter state dict for card embeddings
        
        Returns:
            torch.Tensor: Shape (output_dim,) containing player state
        """
        features = []
        
        # 1. Health (normalized)
        features.append(torch.tensor([player.health / self.norm_health]))
        
        # 2. Intellect (normalized)
        features.append(torch.tensor([player.intellect / self.norm_intellect]))
        
        # 3. Resources (normalized)
        features.append(torch.tensor([player.resources / self.norm_resources]))
        
        # 4. Action points (normalized)
        features.append(torch.tensor([player.action_points / self.norm_action_points]))
        
        # 5. Weapon exhausted flag
        features.append(torch.tensor([float(player.weapon_exhausted)]))
        
        # 6. Hero power exhausted flag
        features.append(torch.tensor([float(player.hero_power_exhausted)]))
        
        # 7. Arsenal face-up flag (CR 3.3, CR 4.4.3b)
        features.append(torch.tensor([float(player.arsenal_face_up)]))
        
        # 8. Hero marked condition (CR 9.3)
        features.append(torch.tensor([float(player.marked)]))
        
        # 9. Counter types: shared registry with reserved OOV slots.
        counter_counts_map = {counter_type: 0.0 for counter_type in COUNTER_TYPES}
        for (_, _, counter_type), count in player.counters.items():
            bucket = counter_type if counter_type in counter_counts_map else COUNTER_OOV_TYPE
            counter_counts_map[bucket] += float(count)

        counter_counts = [normalize_counter(counter_type, counter_counts_map[counter_type]) for counter_type in COUNTER_TYPES]
        features.append(torch.tensor(counter_counts))
        
        # 10. Zone sizes (7 zones, added inventory)
        zone_sizes = torch.tensor([
            len(player.hand) / self.norm_zone_size,
            len(player.deck) / self.norm_zone_size,
            len(player.graveyard) / self.norm_zone_size,
            len(player.arsenal) / self.norm_zone_size,
            len(player.banished) / self.norm_zone_size,
            len(player.pitch) / self.norm_zone_size,
            len(player.inventory) / self.norm_zone_size,
        ])
        features.append(zone_sizes)
        
        # 11. Equipment cards (6 slots per CR 3.0.2: head, chest, arms, legs, weapon1, weapon2)
        equipment_zones = [player.head, player.chest, player.arms, player.legs, player.weapon1, player.weapon2]
        for equip_zone in equipment_zones:
            if equip_zone.cards:
                # Take first card in zone (equipment slots have 1 card each)
                equip_emb = self.embed_card(equip_zone.cards[0], player_counters)
            else:
                equip_emb = torch.zeros(self.d_model)
            features.append(equip_emb)
        
        # 11b. Equipment exhausted flags (6 slots for "Once per Turn" tracking)
        equipment_exhausted = []
        for equip_zone in equipment_zones:
            if equip_zone.cards:
                equipment_exhausted.append(float(equip_zone.cards[0].exhausted))
            else:
                equipment_exhausted.append(0.0)
        features.append(torch.tensor(equipment_exhausted))

        # 11c. Equipment tapped flags (6 slots, separate from exhausted)
        equipment_tapped = []
        for equip_zone in equipment_zones:
            if equip_zone.cards:
                equipment_tapped.append(float(equip_zone.cards[0].tapped))
            else:
                equipment_tapped.append(0.0)
        features.append(torch.tensor(equipment_tapped))
        
        # 12. Permanents zone embedding (sum pool) + explicit count.
        # Sum pooling preserves board scale; count keeps cardinality explicit.
        permanent_cards = list(player.permanents.cards) + list(player.soul.cards)
        if permanent_cards:
            perm_embs = [self.embed_card(card, player_counters) for card in permanent_cards]
            permanents_emb = sum(perm_embs)
            permanents_count = min(float(len(permanent_cards)), 20.0) / 20.0
        else:
            permanents_emb = torch.zeros(self.d_model)
            permanents_count = 0.0
        features.append(permanents_emb)
        features.append(torch.tensor([permanents_count]))
        
        # Concatenate all features
        player_embedding = torch.cat(features)
        
        return player_embedding


class GlobalStateEmbedder(nn.Module):
    """Embeds global game state (turn, combat, stack, chain).
    
    Features:
    - Turn number: 1-dim normalized
    - Active player: 1-dim binary
    - Step: 11-dim one-hot
    - Priority player: 1-dim binary
    - Consecutive passes: 1-dim normalized
    - Combat state: 13-dim + len(CARD_KEYWORDS) + 4*d_model
    - Stack state: 5 * (8 + d_model) + (11 + 2*d_model) summary
    - Chain links: 3-dim aggregated
    
    Total: 218 + len(CARD_KEYWORDS) + 11*d_model (Round 10: includes stack-layer details,
    event history, continuous effects, replacement effects, trigger metadata)
    """
    
    def __init__(self, d_model: int = 128, card_embedder: Optional[CardEmbedder] = None, slug_vocab_size: int = 4563, slug_vocab: Optional[SlugVocab] = None):
        super().__init__()
        self.d_model = d_model
        self.slug_vocab = slug_vocab
        
        if card_embedder is None:
            self.card_embedder = CardEmbedder(slug_vocab_size=slug_vocab_size, d_model=d_model)
        else:
            self.card_embedder = card_embedder
        
        # Step embedding: 11-dim one-hot → 64-dim projection
        self.step_embed = nn.Linear(len(STEPS), 64)
        
        # Normalization constants
        self.norm_turn = 20.0
        self.norm_passes = 5.0
        self.norm_attack_power = 20.0
        self.norm_defense = 20.0
        self.norm_stack_size = 10.0
    
    def embed_card(self, card: Optional[Card], player_counters: Optional[dict] = None) -> torch.Tensor:
        """Helper to embed a single card using card_to_features."""
        if card is None or self.slug_vocab is None:
            return torch.zeros(self.d_model)
        
        features = card_to_features(card, self.slug_vocab, player_counters=player_counters)
        # Add batch dimension
        features = {k: v.unsqueeze(0) if v.dim() == 0 or (v.dim() == 1 and k not in ["numeric", "types", "subtypes", "supertypes", "keywords"]) else v.unsqueeze(0) 
                   for k, v in features.items()}
        emb = self.card_embedder(features)
        return emb.squeeze(0)  # Remove batch dim
    
    def get_output_dim(self) -> int:
        """Total output dimension: 
        - Turn: 1
        - Active player: 1
        - Step embed: 64
        - Priority: 1
        - Consecutive passes: 1
        - Combat: 13 + len(CARD_KEYWORDS) + 4*d_model
        - Stack layers: 5 * (8 + d_model) = 40 + 5*d_model
        - Stack summary: 11 + 2*d_model
        - Chain links: 3
        - Event history: 15
        - Continuous effects summary: 30
        - Replacement effects summary: 36
        - Trigger metadata summary: 2
        Total: 218 + len(CARD_KEYWORDS) + 11*d_model
        With d_model=128 and current keyword registry: 1694 dimensions
        """
        return 218 + len(CARD_KEYWORDS) + 11 * self.d_model

    @staticmethod
    def _enum_to_str(value) -> str:
        if value is None:
            return ""
        if hasattr(value, "value"):
            value = value.value
        text = str(value).lower()
        if "." in text:
            text = text.split(".")[-1]
        return text

    def _encode_continuous_effects(self, state: GameState) -> torch.Tensor:
        """Encode active continuous effects from EffectManager into 30 dims."""
        fx_manager = getattr(state, 'effect_manager', None)
        effects = list(getattr(fx_manager, 'continuous_effects', []) or [])

        norm_count = 20.0

        stage_hist = torch.zeros(8)
        mod_hist = torch.zeros(7)
        source_hist = torch.zeros(2)  # layer/static
        duration_hist = torch.zeros(4)  # end_of_turn, end_of_next_turn, permanent, other
        owner_hist = torch.zeros(2)  # p1 / p2
        consumed_count = 0.0

        mod_name_to_idx = {
            'add_property': 0,
            'set': 1,
            'multiply': 2,
            'divide': 3,
            'add': 4,
            'subtract': 5,
            'dependent': 6,
        }

        def _safe_int(value, default=0) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        for effect in effects:
            # Stage histogram (1..8)
            stage_raw = getattr(effect, 'stage', 0)
            stage = _safe_int(stage_raw, 0)
            if 1 <= stage <= 8:
                stage_hist[stage - 1] += 1.0

            # Mod type histogram (1..7 or enum/string name)
            mod_raw = getattr(effect, 'mod_type', None)
            mod_idx = None
            if mod_raw is not None:
                if hasattr(mod_raw, 'value'):
                    mod_raw = mod_raw.value
                if isinstance(mod_raw, int) and 1 <= mod_raw <= 7:
                    mod_idx = mod_raw - 1
                else:
                    mod_name = self._enum_to_str(mod_raw)
                    mod_idx = mod_name_to_idx.get(mod_name)
            if mod_idx is not None:
                mod_hist[mod_idx] += 1.0

            # Source type histogram
            source_type = self._enum_to_str(getattr(effect, 'source_type', None))
            if source_type == 'layer':
                source_hist[0] += 1.0
            elif source_type == 'static':
                source_hist[1] += 1.0

            # Duration histogram
            duration = str(getattr(effect, 'duration', None) or 'none').lower()
            if duration == 'end_of_turn':
                duration_hist[0] += 1.0
            elif duration == 'end_of_next_turn':
                duration_hist[1] += 1.0
            elif duration == 'permanent':
                duration_hist[2] += 1.0
            else:
                duration_hist[3] += 1.0

            # Owner histogram
            owner_raw = getattr(effect, 'owner_id', 0)
            try:
                owner = int(owner_raw)
            except (TypeError, ValueError):
                owner = 0
            if owner in (1, 2):
                owner_hist[owner - 1] += 1.0

            consumed_count += float(bool(getattr(effect, 'consumed', False)))

        if effects:
            ordered_effects = sorted(
                effects,
                key=lambda e: (
                    _safe_int(getattr(e, 'stage', 0), 0),
                    _safe_int(getattr(e, 'substage', 0), 0),
                    _safe_int(getattr(e, 'timestamp', 0), 0),
                ),
            )
            first_effect = ordered_effects[0]
            last_effect = ordered_effects[-1]
            first_stage = _safe_int(getattr(first_effect, 'stage', 0), 0)
            first_substage = _safe_int(getattr(first_effect, 'substage', 0), 0)
            last_stage = _safe_int(getattr(last_effect, 'stage', 0), 0)
            last_substage = _safe_int(getattr(last_effect, 'substage', 0), 0)
            first_ts = _safe_int(getattr(first_effect, 'timestamp', 0), 0)
            last_ts = _safe_int(getattr(last_effect, 'timestamp', 0), 0)

            ordering_features = torch.tensor([
                first_stage / 8.0,
                first_substage / 7.0,
                last_stage / 8.0,
                last_substage / 7.0,
                max(0.0, float(last_ts - first_ts)) / norm_count,
            ])
        else:
            ordering_features = torch.zeros(5)

        effect_count = len(effects)
        return torch.cat([
            torch.tensor([
                effect_count / norm_count,
                consumed_count / norm_count,
            ]),
            stage_hist / norm_count,
            mod_hist / norm_count,
            source_hist / norm_count,
            duration_hist / norm_count,
            owner_hist / norm_count,
            ordering_features,
        ])

    def _encode_replacement_effects(self, state: GameState) -> torch.Tensor:
        """Encode active replacement effects from EffectManager into 36 dims."""
        fx_manager = getattr(state, 'effect_manager', None)
        effects = list(getattr(fx_manager, 'replacement_effects', []) or [])

        norm_count = 20.0
        norm_prevention = 40.0

        type_hist = torch.zeros(5)  # self, identity, standard, prevention, outcome
        owner_hist = torch.zeros(2)

        type_to_idx = {
            'self': 0,
            'identity': 1,
            'standard': 2,
            'prevention': 3,
            'outcome': 4,
        }

        shielding_count = 0.0
        consumed_count = 0.0
        total_prevention = 0.0
        ordered_type_indices: list[int] = []

        for effect in effects:
            replacement_type = self._enum_to_str(getattr(effect, 'replacement_type', None))
            idx = type_to_idx.get(replacement_type)
            if idx is not None:
                type_hist[idx] += 1.0
                ordered_type_indices.append(idx)

            owner_raw = getattr(effect, 'owner_id', 0)
            try:
                owner = int(owner_raw)
            except (TypeError, ValueError):
                owner = 0
            if owner in (1, 2):
                owner_hist[owner - 1] += 1.0

            shielding_count += float(bool(getattr(effect, 'is_shielding', False)))
            consumed_count += float(bool(getattr(effect, 'consumed', False)))

            prevention_raw = getattr(effect, 'prevention_amount', 0)
            try:
                total_prevention += float(prevention_raw)
            except (TypeError, ValueError):
                pass

        transition_hist = torch.zeros((5, 5))
        if len(ordered_type_indices) > 1:
            for i in range(1, len(ordered_type_indices)):
                src_idx = ordered_type_indices[i - 1]
                dst_idx = ordered_type_indices[i]
                transition_hist[src_idx, dst_idx] += 1.0
            transition_hist = transition_hist / float(len(ordered_type_indices) - 1)
        transition_features = transition_hist.flatten()

        effect_count = len(effects)
        return torch.cat([
            torch.tensor([
                effect_count / norm_count,
            ]),
            type_hist / norm_count,
            torch.tensor([
                shielding_count / norm_count,
                consumed_count / norm_count,
                total_prevention / norm_prevention,
            ]),
            owner_hist / norm_count,
            transition_features,
        ])

    def _encode_trigger_metadata(self, state: GameState) -> torch.Tensor:
        """Encode pending triggered-layer metadata into 2 dims."""
        stack_entries = list(getattr(state, 'stack_entries', []) or [])

        pending_triggers = 0
        unique_trigger_events = set()

        for entry in stack_entries:
            layer_type = str(getattr(entry, 'layer_type', '')).lower()
            is_triggered = bool(getattr(entry, 'is_triggered', False))
            if layer_type == 'triggered' or is_triggered:
                pending_triggers += 1
                trigger_event = getattr(entry, 'trigger_event', None)
                if trigger_event:
                    unique_trigger_events.add(str(trigger_event))

        return torch.tensor([
            pending_triggers / 10.0,
            len(unique_trigger_events) / 10.0,
        ])
    
    def forward(self, state: GameState, player_counters: Optional[dict] = None) -> torch.Tensor:
        """Convert global state to embedding tensor.
        
        Args:
            state: GameState object
            player_counters: Optional counter state dict
        
        Returns:
            torch.Tensor: Shape (output_dim,) containing global state
        """
        features = []
        
        # 1. Turn number (normalized)
        features.append(torch.tensor([state.turn_number / self.norm_turn]))
        
        # 2. Active player (binary)
        features.append(torch.tensor([float(state.active_player) / 2.0]))
        
        # 3. Step (11-dim one-hot → 64-dim projection)
        try:
            step_idx = STEPS.index(state.step.value)
            step_onehot = torch.zeros(len(STEPS))
            step_onehot[step_idx] = 1.0
        except (ValueError, AttributeError):
            step_onehot = torch.zeros(len(STEPS))
        step_emb = self.step_embed(step_onehot)
        features.append(step_emb)
        
        # 4. Priority player (binary)
        features.append(torch.tensor([float(state.priority_player) / 2.0]))
        
        # 5. Consecutive passes (normalized)
        features.append(torch.tensor([state.consecutive_passes / self.norm_passes]))
        
        # 6. Combat state (13-dim + keywords + 4*d_model if combat active)
        if state.combat is not None:
            # Attack target player ID (CR 1.4.5, 7.2.4b)
            attack_target = getattr(state.combat, 'attack_target', None)
            attack_target_id = attack_target.player_id if hasattr(attack_target, 'player_id') else 0
            # Defending equipment count (CR 7.0.5d, 7.3.2a)
            defending_equip_count = len(state.combat.defending_equipment_zones)
            
            combat_features = torch.tensor([
                float(state.combat.attacker_id) / 2.0,
                float(attack_target_id) / 2.0,  # NEW: attack target
                state.combat.link_id / 10.0,
                state.combat.attack_power / self.norm_attack_power,
                state.combat.base_attack_power / self.norm_attack_power,
                float(state.combat.from_weapon),
                state.combat.total_defense / self.norm_defense,
                state.combat.defending_equipment_defense / self.norm_defense,
                float(defending_equip_count) / 5.0,  # NEW: equipment count
                float(state.combat.defender_used_hand_card),
                float(state.combat.no_defense_reactions),
                float(state.combat.defending_declared),
            ])
            features.append(combat_features)
            
            # Attack card embedding
            attack_emb = self.embed_card(state.combat.attack_card if state.combat.attack_card else None, player_counters)
            features.append(attack_emb)

            # Attack source embedding distinguishes proxy/layer source semantics from attack card.
            attack_source_card = getattr(state.combat, 'attack_source', None)
            if attack_source_card is None and state.combat.from_weapon:
                attack_source_card = state.combat.attack_card
            attack_source_emb = self.embed_card(attack_source_card, player_counters)
            features.append(attack_source_emb)
            
            # Combat keywords multi-hot using shared keyword registry.
            keywords_vec = torch.zeros(len(CARD_KEYWORDS), dtype=torch.float32)
            if state.combat.keywords:
                for kw in state.combat.keywords:
                    kw_idx = _CARD_KEYWORD_IDX.get(kw.lower(), _CARD_KEYWORD_OOV_IDX)
                    if kw_idx == _CARD_KEYWORD_OOV_IDX:
                        keywords_vec[kw_idx] += 1.0
                    else:
                        keywords_vec[kw_idx] = 1.0
            features.append(keywords_vec)
            
            # Defending cards embedding (d_model-dim, sum pool)
            if state.combat.defending_cards:
                defending_embs = [self.embed_card(c, player_counters) for c in state.combat.defending_cards]
                defending_emb = sum(defending_embs)
            else:
                defending_emb = torch.zeros(self.d_model)
            features.append(defending_emb)

            # Defending equipment identity embeddings preserve equipment-specific interactions.
            defender_player = attack_target if hasattr(attack_target, 'zone_by_name') else state.players.get(3 - state.combat.attacker_id)
            defending_equipment_cards = []
            if defender_player is not None:
                for zone_name in state.combat.defending_equipment_zones:
                    equip_zone = defender_player.zone_by_name(zone_name)
                    if equip_zone and equip_zone.cards:
                        defending_equipment_cards.append(equip_zone.cards[0])
            if defending_equipment_cards:
                defending_equip_emb = sum(self.embed_card(c, player_counters) for c in defending_equipment_cards)
            else:
                defending_equip_emb = torch.zeros(self.d_model)
            features.append(defending_equip_emb)

            # Defending card count is explicit for pooling disambiguation.
            defending_count = min(float(len(state.combat.defending_cards)), 30.0) / 30.0
            features.append(torch.tensor([defending_count]))
        else:
            features.append(torch.zeros(12))  # Updated from 10 to 12
            features.append(torch.zeros(self.d_model))
            features.append(torch.zeros(self.d_model))
            features.append(torch.zeros(len(CARD_KEYWORDS)))
            features.append(torch.zeros(self.d_model))
            features.append(torch.zeros(self.d_model))
            features.append(torch.zeros(1))
        
        # 7. Stack layers (5 layers max, detailed per-layer features)
        # Per-layer: [position, type_onehot(3), from_arsenal, declared_x, 
        #             num_modes, num_targets, d_model(card)]
        # = 1 + 3 + 1 + 1 + 1 + 1 + d_model per layer
        # Total: 5 * (8 + d_model) dims
        for i in range(MAX_STACK_LAYERS):
            if i < len(state.stack_entries):
                entry = state.stack_entries[-(i+1)]  # Top of stack is end of list
                
                # Position (normalized)
                position = float(entry.layer_position) / 10.0
                
                # Layer type (3-dim one-hot)
                layer_type_onehot = torch.zeros(3)
                try:
                    type_idx = STACK_LAYER_TYPES.index(entry.layer_type)
                    layer_type_onehot[type_idx] = 1.0
                except (ValueError, AttributeError):
                    layer_type_onehot[0] = 1.0  # Default to 'card'
                
                # From arsenal flag
                from_arsenal = float(entry.from_arsenal)
                
                # Declared X (normalized)
                declared_x = (entry.declared_x or 0.0) / 30.0
                
                # Number of modes declared
                num_modes = float(len(entry.declared_modes)) / 5.0
                
                # Number of targets declared
                num_targets = float(len(entry.declared_targets)) / 5.0
                
                # Card embedding
                card_emb = self.embed_card(entry.card, player_counters)
                
                # Combine layer features
                layer_features = torch.cat([
                    torch.tensor([position]),
                    layer_type_onehot,
                    torch.tensor([from_arsenal, declared_x, num_modes, num_targets]),
                    card_emb
                ])
            else:
                # Empty layer (zeros)
                layer_features = torch.zeros(8 + self.d_model)
            
            features.append(layer_features)

        # Stack summary preserves information from layers beyond MAX_STACK_LAYERS.
        stack_size = len(state.stack_entries)
        stack_overflow = max(0, stack_size - MAX_STACK_LAYERS)
        if state.stack_entries:
            stack_embs = [self.embed_card(entry.card, player_counters) for entry in state.stack_entries]
            stack_pooled_emb = sum(stack_embs)
        else:
            stack_pooled_emb = torch.zeros(self.d_model)

        overflow_entries = state.stack_entries[:-MAX_STACK_LAYERS] if stack_overflow > 0 else []
        overflow_order_features = torch.zeros(9)
        overflow_sequence_emb = torch.zeros(self.d_model)
        if overflow_entries:
            overflow_oldest = overflow_entries[0]
            overflow_newest = overflow_entries[-1]

            oldest_pos = float(getattr(overflow_oldest, 'layer_position', 0)) / self.norm_stack_size
            newest_pos = float(getattr(overflow_newest, 'layer_position', 0)) / self.norm_stack_size
            pos_span = max(0.0, newest_pos - oldest_pos)

            first_type_onehot = torch.zeros(3)
            last_type_onehot = torch.zeros(3)
            first_type = str(getattr(overflow_oldest, 'layer_type', '')).lower()
            last_type = str(getattr(overflow_newest, 'layer_type', '')).lower()
            if first_type in STACK_LAYER_TYPES:
                first_type_onehot[STACK_LAYER_TYPES.index(first_type)] = 1.0
            if last_type in STACK_LAYER_TYPES:
                last_type_onehot[STACK_LAYER_TYPES.index(last_type)] = 1.0

            overflow_order_features = torch.cat([
                torch.tensor([oldest_pos, newest_pos, pos_span]),
                first_type_onehot,
                last_type_onehot,
            ])

            # Sequence-sensitive identity signal across overflow layers.
            num_overflow = float(len(overflow_entries))
            for idx, overflow_entry in enumerate(overflow_entries):
                weight = float(idx + 1) / num_overflow
                overflow_sequence_emb += weight * self.embed_card(getattr(overflow_entry, 'card', None), player_counters)

        stack_summary = torch.cat([
            torch.tensor([
                stack_size / self.norm_stack_size,
                stack_overflow / self.norm_stack_size,
            ]),
            stack_pooled_emb,
            overflow_order_features,
            overflow_sequence_emb,
        ])
        features.append(stack_summary)

        # 8. Chain links aggregated (3-dim: count, avg power, hit rate)
        if state.chain_links:
            num_links = len(state.chain_links)
            avg_power = sum(link.attack_power for link in state.chain_links) / num_links
            hit_rate = sum(link.hit for link in state.chain_links) / num_links
            chain_features = torch.tensor([
                num_links / 10.0,
                avg_power / self.norm_attack_power,
                hit_rate,
            ])
        else:
            chain_features = torch.zeros(3)
        features.append(chain_features)

        # 9. Event history (15-dim, binary flags for this turn)
        # These flags support "if you've X this turn" style effects.
        tracked_events = [
            'card_pitched', 'on_play', 'attacking', 'defend', 'hit',
            'damage_dealt', 'arcane_damage_dealt', 'card_banished', 'card_destroyed',
            'gold_created', 'die_roll', 'crowd_boos',
            'start_of_turn', 'start_of_action_phase', 'start_of_end_phase',
        ]
        events_this_turn = getattr(state, 'events_this_turn', set())
        event_features = torch.tensor([
            1.0 if evt in events_this_turn else 0.0 for evt in tracked_events
        ])
        features.append(event_features)

        # 10. Continuous effects summary (30-dim)
        features.append(self._encode_continuous_effects(state))

        # 11. Replacement effects summary (36-dim)
        features.append(self._encode_replacement_effects(state))

        # 12. Trigger metadata summary (2-dim)
        features.append(self._encode_trigger_metadata(state))
        
        # Concatenate all features
        global_embedding = torch.cat(features)
        
        return global_embedding


class GameStateEmbedder(nn.Module):
    """Full game state embedder combining player and global state.
    
    Architecture (Round 10 + Layer System + Counter Expansion + Event/Effect History):
    - Active player state: 28 + len(COUNTER_TYPES) + 7*d_model
    - Inactive player state: 28 + len(COUNTER_TYPES) + 7*d_model
    - Global state: 218 + len(CARD_KEYWORDS) + 11*d_model

    Total: 274 + 2*len(COUNTER_TYPES) + len(CARD_KEYWORDS) + 25*d_model
    With d_model=128 and current registries: 3628 dimensions
    
    The embedder provides a rich representation of the full game state
    suitable for deep RL value networks and policy networks.
    """
    
    def __init__(self, d_model: int = 128, slug_vocab_size: int = 4563, slug_vocab: Optional[SlugVocab] = None):
        super().__init__()
        self.d_model = d_model
        self.slug_vocab = slug_vocab
        
        # Shared card embedder for all components
        self.card_embedder = CardEmbedder(slug_vocab_size=slug_vocab_size, d_model=d_model)
        
        # Sub-embedders
        self.player_embedder = PlayerStateEmbedder(d_model, card_embedder=self.card_embedder, slug_vocab_size=slug_vocab_size, slug_vocab=slug_vocab)
        self.global_embedder = GlobalStateEmbedder(d_model, card_embedder=self.card_embedder, slug_vocab_size=slug_vocab_size, slug_vocab=slug_vocab)
        
        # Layer normalization
        self.layer_norm = nn.LayerNorm(self.get_output_dim())
    
    def get_output_dim(self) -> int:
        """Total output dimension with shared schema registries."""
        return 274 + (2 * len(COUNTER_TYPES)) + len(CARD_KEYWORDS) + (25 * self.d_model)

    def get_schema_metadata(self) -> dict[str, object]:
        """Return schema metadata bundle for checkpoint compatibility checks."""
        return build_schema_metadata(
            embedder="gamestate_embedder",
            d_model=self.d_model,
            extra={
                "player_output_dim": self.player_embedder.get_output_dim(),
                "global_output_dim": self.global_embedder.get_output_dim(),
                "output_dim": self.get_output_dim(),
            },
        )

    def validate_schema(
        self,
        schema_metadata: Optional[dict[str, object]],
        strict: bool = True,
    ) -> tuple[bool, list[str]]:
        """Validate an incoming schema payload against this embedder's schema."""
        if schema_metadata is None:
            return False, ["schema metadata is missing"]
        return validate_schema_metadata(self.get_schema_metadata(), schema_metadata, strict=strict)
    
    def forward(self, state: GameState, perspective_player: int = 1) -> torch.Tensor:
        """Convert GameState to embedding tensor from a player's perspective.
        
        Args:
            state: GameState object to embed
            perspective_player: Player ID (1 or 2) whose perspective to use
                               (active player features come first)
        
        Returns:
            torch.Tensor: Shape (output_dim,) containing full state embedding
        """
        features = []
        
        # Get player objects from perspective
        if perspective_player == state.active_player:
            my_player = state.active()
            opp_player = state.inactive()
        else:
            my_player = state.inactive()
            opp_player = state.active()
        
        # 1. My player state
        my_state = self.player_embedder(my_player, my_player.counters)
        features.append(my_state)
        
        # 2. Opponent player state
        opp_state = self.player_embedder(opp_player, opp_player.counters)
        features.append(opp_state)

        # 3. Global counters use player-id-prefixed keys to avoid cross-player collisions.
        global_player_counters = {}
        for pid, player in state.players.items():
            for (slug, zone, counter_type), count in player.counters.items():
                global_player_counters[(pid, slug, zone, counter_type)] = count
        
        # 4. Global state
        global_state = self.global_embedder(state, global_player_counters)
        features.append(global_state)
        
        # Concatenate all features
        state_embedding = torch.cat(features)
        
        # Normalize
        state_embedding = self.layer_norm(state_embedding)
        
        return state_embedding


def gamestate_to_features(state: GameState) -> dict:
    """Convert GameState to raw feature dict for inspection/debugging.
    
    Returns:
        dict with keys:
            turn: int
            step: str
            active_player: int
            priority_player: int
            p1_health: int
            p2_health: int
            p1_hand_size: int
            p2_hand_size: int
            combat_active: bool
            stack_size: int
            chain_length: int
    """
    p1 = state.players[1]
    p2 = state.players[2]
    
    return {
        "turn": state.turn_number,
        "step": state.step.value if hasattr(state.step, 'value') else str(state.step),
        "active_player": state.active_player,
        "priority_player": state.priority_player,
        "p1_health": p1.health,
        "p2_health": p2.health,
        "p1_hand_size": len(p1.hand),
        "p2_hand_size": len(p2.hand),
        "p1_resources": p1.resources,
        "p2_resources": p2.resources,
        # True if a combat chain exists OR if we are in any combat sub-step
        # (combat_layer fires before state.combat is created — CR 7.1)
        "combat_active": (
            state.combat is not None
            or (state.step is not None and state.step.value.startswith("combat_"))
        ),
        "stack_size": len(state.stack),
        "chain_length": len(state.chain_links),
    }


if __name__ == "__main__":
    # Example usage / testing
    from engine.card import CardDB
    from engine.state import GameState, Player, Step
    from encoder.card_embedder import SlugVocab
    
    # Load card database
    card_db = CardDB()
    
    # Create slug vocab
    slug_vocab = SlugVocab.from_card_db(card_db)
    
    # Create minimal example game state
    hero1 = card_db.get("bravo_showstopper")
    hero2 = card_db.get("rhinar_reckless_rampage")
    
    p1 = Player(player_id=1, hero_card=hero1)
    p2 = Player(player_id=2, hero_card=hero2)
    
    state = GameState(
        players={1: p1, 2: p2},
        active_player=1,
        player_agents={},
        step=Step.ACTION,
        turn_number=1,
        combat=None,
        done=False,
        winner=None,
    )
    
    # Embed game state
    embedder = GameStateEmbedder(d_model=128, slug_vocab_size=slug_vocab.size, slug_vocab=slug_vocab)
    state_emb = embedder(state, perspective_player=1)
    
    print(f"GameState features: {gamestate_to_features(state)}")
    print(f"GameState embedding shape: {state_emb.shape}")
    print(f"Expected dimension: {embedder.get_output_dim()}")
    print(f"GameState embedding: {state_emb[:10]}...")  # First 10 dims
