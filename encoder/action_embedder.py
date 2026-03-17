"""Action embedder for FAB AI agents.

Converts Action objects into fixed-size neural network embeddings suitable for:
- Policy network outputs (action selection)
- Value network inputs (state-action pair evaluation)
- Q-learning action representations

Architecture:
- ActionType: 17-dim one-hot → 64-dim projection (PASS, ATTACK_WEAPON, PLAY_CARD, etc.)
- Player ID: 1-dim binary (0 or 1)
- Card: d_model-dim from CardEmbedder (if present)
- Card index: 1-dim normalized (position in hand/zone)
- Pitch cards: d_model-dim aggregated from CardEmbedder (sum pool)
- From arsenal: 1-dim binary
- Slot: 4-dim one-hot → 32-dim projection (Head, Chest, Arms, Legs)
- Card list: d_model-dim aggregated (for defend actions)
- Attack source: d_model-dim embedding for attack proxy/layer source object
- Attack modality flags: attack_proxy, attack_layer, attack_card (3-dim)
- Targets: pooled d_model-dim from CardEmbedder + 1 target-count scalar
- Phase: 3-dim one-hot → 32-dim projection (start, action, end)
- Step: 14-dim one-hot → 32-dim projection (combat steps, turn boundaries)
- Chain link number: 1-dim normalized
- Priority player: 1-dim binary
- Action economy (5): action_points, resources, action_cost, resource_cost, has_go_again
- Action speed (3): is_instant_speed, is_action_speed, played_as_instant
- Modal choices (18): modes_selected(6-dim ordered sequence), x_value, is_melded, alt_cost(10-dim one-hot)

Total: 64 + 1 + 5*d_model + 1 + 1 + 32 + 32 + 35 + 11 + 18 = 195 + 5*d_model dimensions
With d_model=128: 835 dimensions
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import torch
import torch.nn as nn
import logging
from typing import Optional

from engine.actions import Action, ActionType
from encoder.card_embedder import CardEmbedder, SlugVocab, card_to_features
from encoder.feature_schema import (
    ACTION_ALT_COST_TYPES,
    PHASE_VOCABULARY,
    STEP_VOCABULARY,
    build_schema_metadata,
    validate_schema_metadata,
)
from engine.card import Card

logger = logging.getLogger(__name__)


# Action type vocabulary (17 types from ActionType enum)
ACTION_TYPES = [
    "pass", "attack_weapon", "play_card", "play_arsenal", "defend_cards",
    "defend_equipment", "store_arsenal", "play_attack_reaction",
    "play_defense_reaction", "reaction_pass", "activate_item",
    "attack_ally", "activate_equipment", "activate_weapon",
    "activate_hero", "discard_activate", "play_banish"
]

# Equipment slot vocabulary (4 slots per CR 8.2.10a - Off-Hand is weapon subtype, not equipment)
EQUIPMENT_SLOTS = ["Head", "Chest", "Arms", "Legs"]

# Phase vocabulary (3 phases from CR 4.0.3)
PHASES = PHASE_VOCABULARY
STEPS = STEP_VOCABULARY


class ActionEmbedder(nn.Module):
    """Neural network module that embeds Action objects into fixed-size vectors.
    
    Architecture:
    - Categorical features use multi-hot or one-hot encoding
    - Card objects use CardEmbedder (shared d_model=128)
    - Multiple cards are aggregated via sum pooling
    - All features concatenated into single vector
    
    Args:
        d_model: Embedding dimension for card embeddings (default 128)
        card_embedder: Shared CardEmbedder instance (optional)
    """
    
    def __init__(self, d_model: int = 128, card_embedder: Optional[CardEmbedder] = None, slug_vocab_size: int = 4563, slug_vocab: Optional[SlugVocab] = None):
        super().__init__()
        self.d_model = d_model
        
        # Store vocab for card embedding
        self.slug_vocab = slug_vocab
        
        # Shared card embedder (can be passed in for weight sharing)
        if card_embedder is None:
            self.card_embedder = CardEmbedder(slug_vocab_size=slug_vocab_size, d_model=d_model)
        else:
            self.card_embedder = card_embedder

        # Lazily initialized to avoid loading the DB unless slug lookups are needed.
        self._card_db = None
        
        # Action type embedding: 17-dim one-hot → d_model projection
        self.action_type_embed = nn.Linear(len(ACTION_TYPES), 64)
        
        # Slot embedding: 4-dim one-hot → 32-dim projection
        self.slot_embed = nn.Linear(len(EQUIPMENT_SLOTS), 32)
        
        # Phase embedding: 3-dim one-hot → 32-dim projection (CR 4.0.3)
        self.phase_embed = nn.Linear(len(PHASES), 32)
        
        # Step embedding: 14-dim one-hot → 32-dim projection (CR 4.0.4)
        self.step_embed = nn.Linear(len(STEPS), 32)
        
        # Feature normalization
        self.layer_norm = nn.LayerNorm(self.get_output_dim())
    
    def embed_card(self, card: Optional[Card], player_counters: Optional[dict] = None) -> torch.Tensor:
        """Helper to embed a single card using card_to_features."""
        if card is None or self.slug_vocab is None:
            return torch.zeros(self.d_model)
        
        features = card_to_features(card, self.slug_vocab, player_counters=player_counters)
        # Add batch dimension
        features = {k: v.unsqueeze(0) if v.dim() == 0 or (v.dim() == 1 and k != "numeric" and k != "types" and k != "subtypes" and k != "supertypes" and k != "keywords") else v.unsqueeze(0) 
                   for k, v in features.items()}
        emb = self.card_embedder(features)
        return emb.squeeze(0)  # Remove batch dim

    def _get_card_db(self):
        """Lazily load CardDB for slug->Card resolution."""
        if self._card_db is None:
            from engine.card import CardDB

            self._card_db = CardDB()
        return self._card_db

    def _embed_targets(
        self,
        action: Action,
        player_counters: Optional[dict] = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Encode declared targets using pooled embeddings plus explicit target count."""
        target_cards: list[Card] = []

        if action.targets:
            if self.slug_vocab is not None:
                card_db = self._get_card_db()
                for target_slug in action.targets:
                    card_obj = card_db.get(target_slug)
                    if card_obj is not None:
                        target_cards.append(card_obj)

            # Fallback for legacy single-target actions that also set action.target.
            if not target_cards and action.target is not None:
                target_cards.append(action.target)

            declared_target_count = len(action.targets)
        else:
            if action.target is not None:
                target_cards.append(action.target)
            declared_target_count = 1 if action.target is not None else 0

        if target_cards:
            target_emb = sum(self.embed_card(card, player_counters) for card in target_cards)
        else:
            target_emb = torch.zeros(self.d_model)

        target_count = min(float(declared_target_count), 10.0) / 10.0
        return target_emb, torch.tensor([target_count])
    
    def get_output_dim(self) -> int:
        """Calculate total output dimension.
        
        Components:
        - Action type projection: 64
        - Player ID: 1
        - Card embedding: d_model (128)
        - Card index: 1
        - Pitch cards embedding: d_model (128)
        - From arsenal flag: 1
        - Slot projection: 32
        - Card list embedding: d_model (128)
        - Attack source embedding: d_model (128)
        - Attack modality flags: 3
        - Target embedding: d_model (128)
        - Target count: 1
        - Phase projection: 32
        - Step projection: 32
        - Chain link number: 1
        - Priority player: 1
        - Action points available: 1
        - Resources available: 1
        - Action cost: 1
        - Resource cost: 1
        - Has go again: 1
        - Is instant speed: 1
        - Is action speed: 1
        - Played as instant: 1
        - Modes selected: 6 (ordered sequence, Round 11 - preserve CR 1.7.5 mode order)
        - X-value declared: 1 (Round 9 - normalized by /30.0)
        - Is melded: 1 (Round 9)
        - Alternative cost type: 10 (one-hot, Round 9 - 8 verified types + other + none)
        
        Total: 64 + 1 + 5*d_model + 1 + 1 + 32 + 32 + 3 + 32 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 6 + 1 + 1 + 10 = 835 dimensions
        """
        _n_alt = len(ACTION_ALT_COST_TYPES) + 2  # named types + "other" + "none"
        return 64 + 1 + 5*self.d_model + 1 + 1 + 32 + 32 + 3 + 32 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 6 + 1 + 1 + _n_alt

    def get_schema_metadata(self) -> dict[str, object]:
        """Return schema metadata bundle for checkpoint compatibility checks."""
        return build_schema_metadata(
            embedder="action_embedder",
            d_model=self.d_model,
            extra={
                "output_dim": self.get_output_dim(),
                "num_action_types": len(ACTION_TYPES),
                "num_equipment_slots": len(EQUIPMENT_SLOTS),
                "num_alt_cost_types": len(ACTION_ALT_COST_TYPES),
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
    
    def forward(self, action: Action, player_counters: Optional[dict] = None) -> torch.Tensor:
        """Convert Action to embedding tensor.
        
        Args:
            action: Action object to embed
            player_counters: Optional counter state dict for card embeddings
        
        Returns:
            torch.Tensor: Shape (output_dim,) containing action embedding
        """
        features = []
        
        # 1. Action type (17-dim one-hot → 64-dim projection)
        action_type_idx = ACTION_TYPES.index(action.type.value)
        action_type_onehot = torch.zeros(len(ACTION_TYPES))
        action_type_onehot[action_type_idx] = 1.0
        action_type_emb = self.action_type_embed(action_type_onehot)
        features.append(action_type_emb)
        
        # 2. Player ID (1-dim binary)
        player_id_normalized = float(action.player_id or 0) / 2.0
        features.append(torch.tensor([player_id_normalized]))
        
        # 3. Card embedding (d_model-dim, zero if no card)
        card_emb = self.embed_card(action.card, player_counters)
        features.append(card_emb)
        
        # 4. Card index (1-dim normalized, -1.0 if not present)
        card_idx_normalized = (action.card_idx / 10.0) if action.card_idx is not None else -1.0
        features.append(torch.tensor([card_idx_normalized]))
        
        # 5. Pitch cards embedding (d_model-dim, sum pool over pitch cards)
        if action.pitch_cards and self.slug_vocab is not None:
            card_db = self._get_card_db()
            pitch_card_objs = []
            for item in action.pitch_cards:
                slug = item.slug if hasattr(item, 'slug') else str(item)
                card_obj = card_db.get(slug)
                if card_obj is not None:
                    pitch_card_objs.append(card_obj)
            if pitch_card_objs:
                pitch_embs = [self.embed_card(c, player_counters) for c in pitch_card_objs]
                pitch_emb = sum(pitch_embs)
            else:
                pitch_emb = torch.zeros(self.d_model)
        else:
            pitch_emb = torch.zeros(self.d_model)
        features.append(pitch_emb)
        
        # 6. From arsenal flag (1-dim binary)
        features.append(torch.tensor([float(action.from_arsenal)]))
        
        # 7. Slot (4-dim one-hot → 32-dim projection, zero if no slot)
        if action.slot is not None:
            try:
                slot_idx = EQUIPMENT_SLOTS.index(action.slot)
                slot_onehot = torch.zeros(len(EQUIPMENT_SLOTS))
                slot_onehot[slot_idx] = 1.0
                slot_emb = self.slot_embed(slot_onehot)
            except ValueError:
                # Slot not in vocabulary (e.g., "weapon", "items")
                slot_emb = torch.zeros(32)
        else:
            slot_emb = torch.zeros(32)
        features.append(slot_emb)
        
        # 8. Card list embedding (d_model-dim, sum pool for defend actions)
        if action.card_list:
            card_list_embs = [self.embed_card(c, player_counters) for c in action.card_list]
            card_list_emb = sum(card_list_embs)
        else:
            card_list_emb = torch.zeros(self.d_model)
        features.append(card_list_emb)

        # 9. Attack-source embedding + attack modality flags.
        # CR 1.4.3/1.4.4: attack may be represented by proxy/layer distinct from card object.
        attack_source_card = action.attack_source
        if attack_source_card is None and action.type in (ActionType.ATTACK_WEAPON, ActionType.ATTACK_ALLY):
            attack_source_card = action.card
        attack_source_emb = self.embed_card(attack_source_card, player_counters)
        features.append(attack_source_emb)

        attack_proxy = action.is_attack_proxy
        if attack_proxy is None:
            attack_proxy = action.type in (ActionType.ATTACK_WEAPON, ActionType.ATTACK_ALLY)
        attack_layer = bool(action.is_attack_layer)
        attack_card = bool(action.card is not None and not attack_layer)
        features.append(torch.tensor([
            float(attack_proxy),
            float(attack_layer),
            float(attack_card),
        ]))
        
        # 10. Targets embedding + target count (supports multi-target declarations)
        target_emb, target_count = self._embed_targets(action, player_counters)
        features.append(target_emb)
        features.append(target_count)
        
        # 11. Phase (3-dim one-hot → 32-dim projection) (CR 4.0.3)
        if action.phase and action.phase in PHASES:
            phase_idx = PHASES.index(action.phase)
            phase_onehot = torch.zeros(len(PHASES))
            phase_onehot[phase_idx] = 1.0
            phase_emb = self.phase_embed(phase_onehot)
        else:
            phase_emb = torch.zeros(32)
        features.append(phase_emb)
        
        # 12. Step (14-dim one-hot → 32-dim projection) (CR 4.0.4)
        if action.step:
            try:
                step_value = action.step.value if hasattr(action.step, 'value') else str(action.step)
                step_idx = STEPS.index(step_value)
                step_onehot = torch.zeros(len(STEPS))
                step_onehot[step_idx] = 1.0
                step_emb = self.step_embed(step_onehot)
            except (ValueError, AttributeError):
                step_emb = torch.zeros(32)
        else:
            step_emb = torch.zeros(32)
        features.append(step_emb)
        
        # 13. Chain link number (1-dim normalized) (CR 7.0.3b)
        chain_link_norm = (action.chain_link_number or 0) / 10.0  # Aligned with gamestate_embedder
        features.append(torch.tensor([chain_link_norm]))
        
        # 14. Priority player (1-dim binary) (CR 1.10)
        priority_norm = float(action.priority_player or 0) / 2.0
        features.append(torch.tensor([priority_norm]))
        
        # 15. Action points available (1-dim normalized) (CR 4.3.2)
        action_points_norm = (action.action_points_available or 0) / 1.0
        features.append(torch.tensor([action_points_norm]))
        
        # 16. Resources available (1-dim normalized) (CR 5.1.6)
        resources_norm = (action.resources_available or 0) / 6.0  # FAB games commonly have 3-4+ resources
        features.append(torch.tensor([resources_norm]))
        
        # 17. Action cost (1-dim binary) (CR 8.1.1c)
        action_cost_norm = float(action.action_cost or 0)
        features.append(torch.tensor([action_cost_norm]))
        
        # 18. Resource cost (1-dim normalized) (CR 5.1.7)
        resource_cost_norm = (action.resource_cost or 0) / 10.0
        features.append(torch.tensor([resource_cost_norm]))
        
        # 19. Has go again (1-dim binary) (CR 8.3.5)
        go_again_flag = float(action.has_go_again or False)
        features.append(torch.tensor([go_again_flag]))
        
        # 20. Is instant speed (1-dim binary) (CR 8.1.6a)
        instant_speed_flag = float(action.is_instant_speed or False)
        features.append(torch.tensor([instant_speed_flag]))
        
        # 21. Is action speed (1-dim binary) (CR 8.1.1a/b)
        action_speed_flag = float(action.is_action_speed or False)
        features.append(torch.tensor([action_speed_flag]))
        
        # 22. Played as instant (1-dim binary) (CR 8.1.1d)
        played_instant_flag = float(action.played_as_instant or False)
        features.append(torch.tensor([played_instant_flag]))
        
        # 23-26. Modal and optional choices (Round 9 - Gap #1 fix +10 points)
        # 23. Modes selected (6-dim ordered sequence for up to 6 selected modes) (CR 1.7.5b, 1.7.5c)
        # Each position stores (mode_idx + 1)/6 so 0.0 can represent an empty slot.
        # Repeated mode choices remain distinct because they occupy separate positions.
        modes_vec = torch.zeros(6)
        if action.modes_selected:
            for position, mode_idx in enumerate(action.modes_selected[:6]):
                if 0 <= mode_idx < 6:
                    modes_vec[position] = float(mode_idx + 1) / 6.0
                else:
                    logger.warning(f"Mode index {mode_idx} exceeds max 6 modes - ignoring")
        features.append(modes_vec)
        
        # 24. X-value declared (1-dim normalized) (CR 1.12.2, 5.1.3a)
        # Normalized to [0, ~1.0] range (max ~30 for resource accumulation)
        # Capped at 2.0 to prevent gradient instability for extreme X values
        x_value_norm = min((action.x_value_declared or 0) / 30.0, 2.0)
        features.append(torch.tensor([x_value_norm]))
        
        # 25. Is melded (1-dim binary) (CR 8.3.38, 5.1.2c)
        meld_flag = float(action.is_melded or False)
        features.append(torch.tensor([meld_flag]))
        
        # 26. Alternative cost type (10-dim one-hot) (CR 5.1.3c, 8.3.38a)
        # Verified alternative costs: rune_gate, cash_in, rise_above, life_of_party, double_down, reunion, soul_reaping, meld
        _n_alt = len(ACTION_ALT_COST_TYPES)
        alt_cost_vec = torch.zeros(_n_alt + 2)  # named types + "other" + "none"
        if action.alternative_cost_used:
            try:
                idx = ACTION_ALT_COST_TYPES.index(action.alternative_cost_used)
                alt_cost_vec[idx] = 1.0
            except ValueError:
                logger.warning(f"Unknown alternative cost type: '{action.alternative_cost_used}' - using 'other' category")
                alt_cost_vec[_n_alt] = 1.0  # "other" category
        else:
            alt_cost_vec[_n_alt + 1] = 1.0  # "none" category
        features.append(alt_cost_vec)
        
        # Concatenate all features
        action_embedding = torch.cat(features)
        
        # Normalize
        action_embedding = self.layer_norm(action_embedding)
        
        return action_embedding


def action_to_features(action: Action) -> dict:
    """Convert Action to raw feature dict for inspection/debugging.
    
    Returns:
        dict with keys:
            action_type: str
            player_id: int
            has_card: bool
            card_idx: Optional[int]
            num_pitch_cards: int
            from_arsenal: bool
            slot: Optional[str]
            num_defend_cards: int
            has_target: bool
            num_targets: int
            has_attack_source: bool
            is_attack_proxy: bool
            is_attack_layer: bool
            phase: Optional[str]
            step: Optional[str]
            chain_link_number: Optional[int]
            priority_player: Optional[int]
            action_points_available: Optional[int]
            resources_available: Optional[int]
            action_cost: Optional[int]
            resource_cost: Optional[int]
            has_go_again: Optional[bool]
            is_instant_speed: Optional[bool]
            is_action_speed: Optional[bool]
            played_as_instant: Optional[bool]
    """
    card_slug = action.card.slug if action.card is not None else None
    card_name = action.card.name if action.card is not None else None

    pitch_card_slugs = [c.slug for c in (action.pitch_cards or []) if hasattr(c, "slug")]
    pitch_card_names = [c.name for c in (action.pitch_cards or []) if hasattr(c, "name")]

    defend_card_slugs = [c.slug for c in (action.card_list or []) if hasattr(c, "slug")]
    defend_card_names = [c.name for c in (action.card_list or []) if hasattr(c, "name")]

    target_slug = action.target.slug if action.target is not None and hasattr(action.target, "slug") else None
    target_name = action.target.name if action.target is not None and hasattr(action.target, "name") else None

    declared_target_slugs = []
    for target in (action.targets or []):
        if isinstance(target, str):
            declared_target_slugs.append(target)
        elif hasattr(target, "slug"):
            declared_target_slugs.append(target.slug)

    return {
        "action_type": action.type.value,
        "player_id": action.player_id,
        "has_card": action.card is not None,
        "card_slug": card_slug,
        "card_name": card_name,
        "card_idx": action.card_idx,
        "num_pitch_cards": len(action.pitch_cards),
        "pitch_card_slugs": pitch_card_slugs,
        "pitch_card_names": pitch_card_names,
        "from_arsenal": action.from_arsenal,
        "slot": action.slot,
        "num_defend_cards": len(action.card_list) if action.card_list else 0,
        "defend_card_slugs": defend_card_slugs,
        "defend_card_names": defend_card_names,
        "has_target": action.target is not None,
        "num_targets": len(action.targets) if action.targets else (1 if action.target is not None else 0),
        "target_slug": target_slug,
        "target_name": target_name,
        "declared_target_slugs": declared_target_slugs,
        "has_attack_source": action.attack_source is not None,
        "is_attack_proxy": bool(action.is_attack_proxy),
        "is_attack_layer": bool(action.is_attack_layer),
        "phase": action.phase,
        "step": action.step.value if action.step else None,
        "chain_link_number": action.chain_link_number,
        "priority_player": action.priority_player,
        "action_points_available": action.action_points_available,
        "resources_available": action.resources_available,
        "action_cost": action.action_cost,
        "resource_cost": action.resource_cost,
        "has_go_again": action.has_go_again,
        "is_instant_speed": action.is_instant_speed,
        "is_action_speed": action.is_action_speed,
        "played_as_instant": action.played_as_instant,
        "modes_selected": list(action.modes_selected) if action.modes_selected else [],
        "x_value_declared": action.x_value_declared,
        "is_melded": bool(action.is_melded),
        "alternative_cost_used": action.alternative_cost_used,
    }


if __name__ == "__main__":
    # Example usage / testing
    from engine.card import CardDB
    from engine.actions import Action, ActionType
    from encoder.card_embedder import SlugVocab
    
    # Load card database
    card_db = CardDB()
    
    # Create slug vocab
    slug_vocab = SlugVocab.from_card_db(card_db)
    
    # Create example action: play a card
    test_card = card_db.get("aether_wildfire_red")
    test_action = Action(
        type=ActionType.PLAY_CARD,
        player_id=1,
        card=test_card,
        card_idx=2,
        pitch_cards=[],
        from_arsenal=False,
    )
    
    # Embed action
    embedder = ActionEmbedder(d_model=128, slug_vocab_size=slug_vocab.size, slug_vocab=slug_vocab)
    action_emb = embedder(test_action)
    
    print(f"Action: {test_action}")
    print(f"Action embedding shape: {action_emb.shape}")
    print(f"Action embedding: {action_emb[:10]}...")  # First 10 dims
    print(f"\nFeatures: {action_to_features(test_action)}")
