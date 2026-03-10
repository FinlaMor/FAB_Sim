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
- Flags: weapon_exhausted, hero_power_exhausted (2-dim)
- Zone sizes: hand, deck, graveyard, arsenal, banished, pitch (6-dim)
- Equipment slots: head, chest, arms, legs, weapon (5 * d_model from CardEmbedder)
- Permanents: items, auras, allies, soul, tokens (5 * d_model aggregated)
- Total per player: 11 + 10*d_model

Global State Features:
- Turn number: 1-dim normalized
- Active player: 1-dim binary
- Step: 12-dim one-hot (BEGIN_GAME, ACTION, COMBAT_*, END_*)
- Priority player: 1-dim binary
- Consecutive passes: 1-dim normalized
- Combat state: 10-dim (attacker, power, keywords, defense) + d_model (attack card) + 52-dim (keywords multi-hot) + d_model (defending cards)
- Stack size: 1-dim normalized
- Stack top card: d_model
- Chain links: 3-dim aggregated (count, avg power, hits)
- Total global: 80 + 3*d_model + 52 = 132 + 3*d_model

Total State Embedding: 2*(11 + 10*d_model) + 132 + 3*d_model = 154 + 23*d_model
With d_model=128: 3098 dimensions
"""

import torch
import torch.nn as nn
from typing import Optional

from engine.state import GameState, Player, Step, CombatState, Zone
from encoder.card_embedder import CardEmbedder, SlugVocab, card_to_features, CARD_KEYWORDS
from engine.card import Card


# Step vocabulary (14 steps per CR 4.0: added start/end phase substeps)
STEPS = [
    "begin_game",
    "start_phase",           # CR 4.2: start of turn events
    "action",
    "combat_layer", "combat_attack",
    "combat_defend", "combat_reaction", "combat_damage",
    "combat_resolution", "combat_close",
    "end_phase_beginning",   # CR 4.4.2: beginning of end phase
    "end_phase_cleanup",     # CR 4.4.3: end-of-turn procedure
    "end_turn",
    "end_game"
]


class PlayerStateEmbedder(nn.Module):
    """Embeds a single Player object into fixed-size vector.
    
    Features:
    - Scalar resources: health, intellect, resources, action_points (4-dim)
    - Binary flags: weapon_exhausted, hero_power_exhausted (2-dim)
    - Zone sizes: hand, deck, graveyard, arsenal, banished, pitch (6-dim)
    - Equipment cards: head, chest, arms, legs, weapon (5 * d_model)
    - Permanent cards: items, auras, allies, soul, tokens (5 * d_model aggregated)
    
    Total: 12 scalar features + 10*d_model card features
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
        """Total output dimension: 56 + 11*d_model (Round 9+: 35 counter types, weapon2 per CR 3.0.2)
        Breakdown: health(1) + intellect(1) + resources(1) + action_points(1) + 
                   weapon_exhausted(1) + hero_power_exhausted(1) + arsenal_face_up(1) + marked(1) +
                   counters(35) + zone_sizes(7) + equipment_cards(6*d_model) + equipment_exhausted(6) + 
                   permanents(5*d_model) = 56 + 11*d_model
        With d_model=128: 1464 dimensions
        """
        return 56 + 11 * self.d_model
    
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
        
        # 9. Counter types (35 types, normalized counts) - Round 9+ expansion
        # Counter keys are (card_slug, zone, counter_type)
        # Includes: property-modifying (CR 1.15.2a), archetype-specific (Ranger/Pirate/Mentor/etc), and hero counters
        counter_types = [
            # Property-modifying counters (CR 1.15.2a)
            "plus_power", "minus_power", "plus_defense", "minus_defense",
            # Common non-property counters
            "steam", "flow", "suspense", "verse", "energy",
            # Archetype-specific counters
            "aim", "doom", "balance", "rust", "storm", "stain", "raze", "gold", "lesson", "frost",
            # Hero counters (Brute, Ice)
            "vigor", "charge",
            # NEW: Additional archetype counters for full coverage
            "blood_debt",  # Runeblade (Viserai)
            "ancestral", "crouching", "hidden",  # Ninja (Katsu/Fai)
            "spectral", "illusion",  # Illusionist (Prism)
            "soul",  # Light heroes (Boltyn/Minerva)
            "rum", "plunder",  # Pirate (Privateer)
            "age",  # Cracked Bauble (MST)
            "seismic",  # Earth (HVY)
            "rage",  # Brute (OUT)
            "fury",  # Ranger (Azalea)
            "inventory",  # Merchant
        ]
        counter_counts = []
        for ctype in counter_types:
            total = sum(count for (slug, zone, ct), count in player.counters.items() if ct == ctype)
            counter_counts.append(total / self.norm_counters)
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
        
        # 11b. Equipment exhausted flags (5 slots for "Once per Turn" tracking)
        equipment_exhausted = []
        for equip_zone in equipment_zones:
            if equip_zone.cards:
                equipment_exhausted.append(float(equip_zone.cards[0].exhausted))
            else:
                equipment_exhausted.append(0.0)
        features.append(torch.tensor(equipment_exhausted))
        
        # 12. Permanent cards (5 types, aggregated via sum pool)
        permanent_zones = [player.items, player.auras, player.allies, player.soul, player.tokens]
        for perm_zone in permanent_zones:
            if perm_zone.cards:
                perm_embs = [self.embed_card(card, player_counters) for card in perm_zone.cards]
                perm_emb = sum(perm_embs) / len(perm_embs)  # Average pool
            else:
                perm_emb = torch.zeros(self.d_model)
            features.append(perm_emb)
        
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
    - Combat state: 10-dim + d_model
    - Stack state: 1-dim + d_model
    - Chain links: 3-dim aggregated
    
    Total: 29 + 2*d_model
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
        - Combat: 12 + d_model + 52 + d_model = 64 + 2*d_model
        - Stack layers: 5 * (8 + d_model) = 40 + 5*d_model
        - Chain links: 3
        - Event history: 15
        Total: 190 + 7*d_model
        With d_model=128: 1086 dimensions
        """
        return 190 + 7 * self.d_model
    
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
        
        # 6. Combat state (10-dim + 51-dim keywords + 2*d_model if combat active)
        if state.combat is not None:
            # Attack target player ID (CR 1.4.5, 7.2.4b)
            attack_target_id = state.combat.attack_target.player_id if state.combat.attack_target else 0
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
            
            # Combat keywords multi-hot (51-dim)
            keywords_vec = torch.zeros(len(CARD_KEYWORDS), dtype=torch.float32)
            if state.combat.keywords:
                for kw in state.combat.keywords:
                    try:
                        kw_idx = CARD_KEYWORDS.index(kw)
                        keywords_vec[kw_idx] = 1.0
                    except ValueError:
                        pass  # Keyword not in vocabulary
            features.append(keywords_vec)
            
            # Defending cards embedding (d_model-dim, sum pool)
            if state.combat.defending_cards:
                defending_embs = [self.embed_card(c, player_counters) for c in state.combat.defending_cards]
                defending_emb = sum(defending_embs)
            else:
                defending_emb = torch.zeros(self.d_model)
            features.append(defending_emb)
        else:
            features.append(torch.zeros(12))  # Updated from 10 to 12
            features.append(torch.zeros(self.d_model))
            features.append(torch.zeros(len(CARD_KEYWORDS)))
            features.append(torch.zeros(self.d_model))
        
        # 7. Stack layers (5 layers max, detailed per-layer features)
        # Per-layer: [position, type_onehot(3), from_arsenal, declared_x, 
        #             num_modes, num_targets, d_model(card)]
        # = 1 + 3 + 1 + 1 + 1 + 1 + d_model per layer
        # Total: 5 * (8 + d_model) dims
        MAX_STACK_LAYERS = 5
        LAYER_TYPES = ['card', 'activated', 'triggered']
        
        for i in range(MAX_STACK_LAYERS):
            if i < len(state.stack_entries):
                entry = state.stack_entries[-(i+1)]  # Top of stack is end of list
                
                # Position (normalized)
                position = float(entry.layer_position) / 10.0
                
                # Layer type (3-dim one-hot)
                layer_type_onehot = torch.zeros(3)
                try:
                    type_idx = LAYER_TYPES.index(entry.layer_type)
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
        
        # Concatenate all features
        global_embedding = torch.cat(features)
        
        return global_embedding


class GameStateEmbedder(nn.Module):
    """Full game state embedder combining player and global state.
    
    Architecture (Round 9 + Layer System + Counter Expansion + Event History):
    - Active player state: 56 + 11*d_model
    - Inactive player state: 56 + 11*d_model
    - Global state: 190 + 7*d_model (includes stack layers with modal/targeting metadata + event history)
    
    Total: 302 + 29*d_model
    With d_model=128: 4014 dimensions
    
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
        """Total output dimension: 2*(56 + 11*d_model) + (190 + 7*d_model) = 302 + 29*d_model 
        With d_model=128: 4014 dimensions"""
        return 302 + 29 * self.d_model
    
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
        
        # Combine player counter dicts for card embeddings
        player_counters = {
            **my_player.counters,
            **opp_player.counters,
        }
        
        # 1. My player state
        my_state = self.player_embedder(my_player, player_counters)
        features.append(my_state)
        
        # 2. Opponent player state
        opp_state = self.player_embedder(opp_player, player_counters)
        features.append(opp_state)
        
        # 3. Global state
        global_state = self.global_embedder(state, player_counters)
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
        "combat_active": state.combat is not None,
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
