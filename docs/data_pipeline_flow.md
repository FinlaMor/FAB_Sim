# Data Pipeline: Talishar -> Model

```
 STAGE 1: RAW TALISHAR API
 ==========================

 GetNextTurn.php returns JSON per decision point:

 +----------------------------------------------------------+
 | Talishar JSON State                                      |
 |                                                          |
 |  playerHealth: 20          opponentHealth: 35            |
 |  playerHand: [{cardNumber: "pummel_red", zone: "HAND",  |
 |     controller: 1, countersMap: {}, keywords: []}, ...]  |
 |  opponentHand: [{...}, ...]                              |
 |  playerEquipment: [{...}, ...]                           |
 |  opponentEquipment: [{...}, ...]                         |
 |  playerArse: [{...}] or null                             |
 |  opponentArse: [{...}] or null                           |
 |  playerDeck: [{...}, ...]                                |
 |  playerDiscard/Banish/Pitch: [{...}, ...]                |
 |  opponentDiscard/Banish/Pitch: [{...}, ...]              |
 |  playerAuras/opponentAuras: [{...}, ...]                 |
 |  activeChainLink: {                                      |
 |    attackingCard: {...},  reactions: [{...}],             |
 |    totalPower: 6,  totalDefense: 3,                      |
 |    goAgain: true, dominate: false, ...                    |
 |  } or null                                               |
 |  combatChainLinks: [{...}, ...]                          |
 |  turnPhase: {turnPhase: "M"}                             |
 +----------------------------------------------------------+

 Available actions: [{mode: 5, cardNumber: "pummel_red", type: "hand"}, ...]
 Action taken:      {mode: 5, cardNumber: "pummel_red", type: "hand"}

                              |
                              | TransitionCollector.record()
                              | (rl_agents/game_data.py)
                              v

 STAGE 2: IN-MEMORY TRANSITION
 ==============================

 +----------------------------------------------------------+
 | Transition Object                                        |
 |                                                          |
 |  game_id:    "a3f2c9b1e7d04..."  (UUID hex)             |
 |  step_idx:   47                                          |
 |  player_id:  1                                           |
 |  turn_number: 8                                          |
 |  state:      {full JSON dict}                            |
 |  next_state: {full JSON dict}                            |
 |  action_taken: {mode, cardNumber, type}                  |
 |  available_actions: [{...}, ...]                         |
 |  reward:     0.0  (finalized later: +1/-1 terminal)      |
 |  done:       false                                       |
 |  p1_hp: 20,  p2_hp: 35                                  |
 |                                                          |
 |  + Denormalized at record time:                          |
 |    decision_type: "play_card"                            |
 |    turn_phase:    "M"                                    |
 |    hand_size: 4,  opp_hand_size: 3                       |
 |    hp_delta: -3,  opp_hp_delta: 0                        |
 |    in_combat_chain: false                                |
 |    game_progress: 0.6  (backfilled after game ends)      |
 |    ...                                                   |
 +----------------------------------------------------------+

 After game ends: collector.finalize_rewards(winner=1)
   winner's last transition: reward = +1.0
   loser's last transition:  reward = -1.0

                              |
                              | GameDataStore.save_transitions()
                              | INSERT INTO transitions/decks
                              v

 STAGE 3: SQLITE DATABASE (talishar_games.db)
 =============================================

 TABLE: decks (1 row per game)
 +----------------------------------------------------------+
 | game_id | p1_hero       | p2_hero       | winner | ...   |
 | "a3f2.."| "katsu_the.." | "bravo_show.."| 1      | ...   |
 | p1_decklist: JSON, p2_decklist: JSON                     |
 | turn_count: 14, total_actions: 87                        |
 +----------------------------------------------------------+

 TABLE: transitions (1 row per decision point, ~500/game)
 +----------------------------------------------------------+
 | id | game_id  | step | player_id | turn_number           |
 | 1  | "a3f2.." | 47   | 1         | 8                     |
 |                                                          |
 | state:             TEXT (full JSON, ~2-5 KB)             |
 | available_actions: TEXT (JSON list)                       |
 | action_taken:      TEXT (JSON dict)                       |
 | next_state:        TEXT (full JSON)                       |
 | reward: 0.0    done: 0                                   |
 |                                                          |
 | decision_type: "play_card"   turn_phase: "M"             |
 | hand_size: 4   hp_delta: -3   game_progress: 0.6        |
 | ...                                                      |
 +----------------------------------------------------------+

 ~4,866 games, ~2.5M transition rows
 (but only ~650 have winner IS NOT NULL)

                              |
                              | build_transformer_hdf5_from_talishar_db()
                              | (rl_agents/dataset_adapter.py)
                              |
                              | For each transition:
                              |   1. json.loads(state)
                              |   2. featurize_state()
                              |   3. featurize_action()
                              |   4. compute RTG rewards
                              v

 STAGE 4: FEATURIZATION (state JSON -> tensors)
 ================================================

 featurize_state() extracts cards from zones in fixed order:

 +--- Card Extraction Order (56 slots) --------+
 | Zone          | Slots  | Max | Source        |
 |---------------|--------|-----|---------------|
 | Hand          | 0-11   | 12  | playerHand    |
 | Equipment     | 12-21  | 10  | playerEquip   |
 | Opp Equipment | 22-31  | 10  | opponentEquip |
 | Arsenal       | 32-33  | 2   | playerArse    |
 | Opp Arsenal   | 34-35  | 2   | opponentArse  |
 | Combat Attack | 36-37  | 2   | chainLink.atk |
 | Combat Defense| 38-43  | 6   | chainLink.def |
 | Auras         | 44-49  | 6   | playerAuras   |
 | Opp Auras     | 50-55  | 6   | opponentAuras |
 +----------------------------------------------+

 Each card slug -> vocab ID via slug_index.json:
   "pummel_red" -> 1847
   (unknown)    -> 1 (UNK)
   (empty slot) -> 0 (PAD)

 card_ids:  [1847, 442, 0, 0, ..., 0]   (56,) int16
 card_zones:[1,    1,   0, 0, ..., 0]   (56,) int8
             ^HAND      ^PAD
 card_mask: [True,True,False,...,False]  (56,) bool

 meta: 28 normalized floats
 +--- Meta Vector (28 features) ---------------------------------+
 | [0]  playerHP / 40           [14] opp_discard_sz / 40         |
 | [1]  opponentHP / 40         [15] opp_banish_sz / 40          |
 | [2]  hand_size / 12          [16] pitch_zone_sz / 20          |
 | [3]  opp_hand_size / 12      [17] opp_pitch_zone_sz / 20     |
 | [4]  deck_size / 80          [18] equipment_count / 10        |
 | [5]  opp_deck_size / 80      [19] opp_equipment_count / 10   |
 | [6]  action_points / 5       [20] has_arsenal (0/1)           |
 | [7]  pitch_count / 10        [21] opp_has_arsenal (0/1)       |
 | [8]  in_combat (0/1)         [22] chain_link_count / 10      |
 | [9]  chain_total_power / 20  [23] go_again (0/1)              |
 | [10] chain_total_def / 20    [24] num_actions / 40            |
 | [11] is_turn_player (0/1)    [25] hp_delta / 20               |
 | [12] discard_size / 40       [26] opp_hp_delta / 20           |
 | [13] banish_size / 40        [27] game_progress (0-1)         |
 +-----------------------------------------------------------------+

 turn_phase_id:    int8  (M=1, B=2, D=3, A=4, ARS=5, P=6, ...)
 decision_type_id: int8  (pass=1, pitch=2, play_card=7, defend_block=4, ...)

 featurize_action():
   card_id: vocab["pummel_red"] = 1847   int16
   mode_id: ACTION_MODE_TO_IDX[5] = 2    int8

 RTG reward computation (reward_mode="rtg"):
   For each player's transitions in a game, backward from terminal:
     run = gamma * run  (gamma=0.97)
     reward[t] = run
   Final step: reward = +1.0 or -1.0
   Step before final: reward = 0.97 * (+/-1.0)
   Two steps before:  reward = 0.97^2 * (+/-1.0)
   ...

                              |
                              | Write to HDF5 in 512-row chunks
                              v

 STAGE 5: HDF5 CACHE (talishar_games_transformer.h5)
 ====================================================

 +--- HDF5 Datasets -------------------------------------------+
 | Dataset                  | Shape      | Dtype   | Example   |
 |--------------------------|------------|---------|-----------|
 | state_card_ids           | (N, 56)    | int16   | [1847,..] |
 | state_card_zones         | (N, 56)    | int8    | [1,1,0..] |
 | state_card_mask          | (N, 56)    | bool    | [T,T,F..] |
 | state_meta               | (N, 28)    | float32 | [0.5,..] |
 | state_turn_phase         | (N,)       | int8    | 1 (=M)    |
 | state_decision_type      | (N,)       | int8    | 7 (=play) |
 | next_state_*             | (same)     | (same)  | ...       |
 | action_card_id           | (N,)       | int16   | 1847      |
 | action_mode_id           | (N,)       | int8    | 2         |
 | reward                   | (N,)       | float32 | 0.912     |
 | done                     | (N,)       | bool    | False     |
 | hero_id                  | (N,)       | int16   | 42        |
 | next_state_hero_id       | (N,)       | int16   | 42        |
 +--------------------------------------------------------------+

 N = 318,801 transitions from 650 completed games
 Attrs: vocab_size=4563, attr_dim=17, max_total_cards=56, meta_dim=28

                              |
                              | TalisharHDF5Dataset.__getitem__(idx)
                              | Memory-mapped read, cast to torch tensors
                              | DataLoader(batch_size=512, shuffle=True)
                              v

 STAGE 6: BATCHED TENSORS (input to model)
 ==========================================

 +--- Batch Dict (B=512) ------+--------+---------+
 | Key              | Shape    | Dtype  | Range   |
 |------------------|----------|--------|---------|
 | s_card_ids       | (512,56) | long   | 0-4563  |
 | s_card_zones     | (512,56) | long   | 0-9     |
 | s_card_mask      | (512,56) | bool   |         |
 | s_meta           | (512,28) | float32| 0-1ish  |
 | s_phase          | (512,)   | long   | 0-8     |
 | s_decision       | (512,)   | long   | 0-11    |
 | ns_*             | (same)   | (same) |         |
 | a_card_id        | (512,)   | long   | 0-4563  |
 | a_mode_id        | (512,)   | long   | 0-9     |
 | reward           | (512,)   | float32| [-1,+1] |
 | done             | (512,)   | float32| 0 or 1  |
 | hero_id          | (512,)   | long   | 0-137   |
 +---------------------------------------------+

 reward *= reward_scale (4.0)  -> range [-4, +4]

                              |
                              | train_batch() in TransformerIQLTrainer
                              v

 STAGE 7: STATE ENCODING (FABTransformerEncoder)
 =================================================

 Step 1: Card Token Construction
 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

 s_card_ids (512, 56) long
      |
      +---> slug_embed: Embedding(4563, 64, pad=0)
      |         -> (512, 56, 64)                       LEARNED
      |
      +---> attr_table[card_ids]: frozen lookup
      |         -> (512, 56, 17)                       FROZEN
      |         [pitch/3, cost/3, power/10, defense/4,
      |          color_r, color_y, color_b,
      |          is_action, is_attack, is_defense_reaction,
      |          is_instant, is_equipment, is_aura, ...]
      |              |
      |              v
      |         attr_proj: Linear(17 -> 48)
      |              -> (512, 56, 48)                  LEARNED
      |
 s_card_zones (512, 56) long
      |
      +---> zone_embed: Embedding(10, 16, pad=0)
                -> (512, 56, 16)                       LEARNED

      cat([slug_emb, zone_emb, attr_emb], dim=-1)
                -> (512, 56, 64+16+48 = 128)
                         |
                         v
                card_proj: Linear(128 -> 128)
                         -> (512, 56, 128)             CARD TOKENS


 Step 2: Meta Token Construction
 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

 s_meta (512, 28) float32
      |
      v
   meta_proj: Linear(28->128) -> GELU -> Linear(128->128)
      -> (512, 128)

      + turn_phase_embed(s_phase):    Embedding(9, 128)  -> (512, 128)
      + decision_type_embed(s_decision): Embedding(12, 128) -> (512, 128)

      -> (512, 1, 128)                                META TOKEN


 Step 3: Sequence Assembly
 ~~~~~~~~~~~~~~~~~~~~~~~~~~~

  [CLS token]     [META token]     [56 Card Tokens]
  (512,1,128)  +  (512,1,128)  +   (512,56,128)
                         |
                         v
              tokens: (512, 58, 128)

              + segment_embed(seg_ids):  Embedding(6, 128)
                seg_ids: [CLS=0, META=1, HAND=2, EQUIP=3, ...]

              + position_embed(pos_ids): Embedding(58, 128)
                pos_ids: [0, 1, 2, ..., 57]

              -> (512, 58, 128)          POSITIONED TOKENS


 Step 4: Transformer
 ~~~~~~~~~~~~~~~~~~~~~~

  tokens (512, 58, 128) + pad_mask (512, 58) bool
      |
      v
  TransformerEncoder:
    3 layers x {
      LayerNorm(128)
      MultiHeadAttention(4 heads, d_model=128, d_k=32)
      Residual + Dropout(0.1)
      LayerNorm(128)
      FFN: Linear(128->256) -> GELU -> Linear(256->128)
      Residual + Dropout(0.1)
    }
      |
      v
  final_norm: LayerNorm(128)
      -> (512, 58, 128)

  Extract CLS: [:, 0, :]
      -> (512, 128)                    STATE EMBEDDING (state_emb)


 STAGE 8: ACTION ENCODING (ActionEncoder)
 ==========================================

 a_card_id (512,) long
      |
      v
 slug_embed: Embedding(4563, 64, pad=0)   <-- SHARED with state encoder
      -> (512, 64)

 a_mode_id (512,) long
      |
      v
 mode_embed: Embedding(10, 32)
      -> (512, 32)

 cat([slug_emb, mode_emb])
      -> (512, 64+32 = 96)
      |
      v
 proj: Linear(96->128) -> GELU -> Linear(128->128) -> LayerNorm(128)
      -> (512, 128)                    ACTION EMBEDDING (action_emb)


 STAGE 9: IQL HEADS
 ====================

 +-- Q-Network (x2: Q1, Q2) --------+
 |                                    |
 |  cat([state_emb, action_emb])      |
 |       -> (512, 256)                |
 |       |                            |
 |       v                            |
 |  MLP: 256->512->ReLU->512->ReLU    |
 |       ->1                          |
 |       -> (512,) scalar Q-values    |
 |                                    |
 |  Q-target (no grad):              |
 |    r + gamma*(1-done)*V_target(ns) |
 |                                    |
 |  Loss: MSE(Q1,target)+MSE(Q2,tgt) |
 |  Grad clip: 1.0                    |
 +------------------------------------+

 +-- V-Network ----------------------+
 |                                    |
 |  state_emb -> (512, 128)           |
 |       |                            |
 |       v                            |
 |  MLP: 128->512->ReLU->512->ReLU    |
 |       ->1                          |
 |       -> (512,) state values       |
 |                                    |
 |  Target: min(Q1,Q2) (stop grad)   |
 |  Loss: expectile(tau=0.7)          |
 |    weight = 0.7 if diff>0 else 0.3 |
 |    loss = weight * diff^2          |
 |  Grad clip: 2.0                    |
 +------------------------------------+

 +-- Actor Network -------------------+
 |                                    |
 |  state_emb -> (512, 128)           |
 |       |                            |
 |       v                            |
 |  MLP: 128->512->ReLU->512->ReLU    |
 |       ->128                        |
 |       -> (512, 128)                |
 |       predicted action embedding   |
 |                                    |
 |  Advantage weights (no grad):     |
 |    adv = min(Q1,Q2) - V(s)        |
 |    adv = normalize(adv)            |
 |    w = exp(temp * adv)             |
 |        .clamp(max=100)             |
 |                                    |
 |  Loss: w * ||pred - action_emb||^2|
 |  Grad clip: 5.0                    |
 +------------------------------------+

 +-- Target V-Network ----------------+
 |  (frozen copy of V-Network)        |
 |  Soft update every step:           |
 |    p_tgt = 0.995*p_tgt + 0.005*p   |
 +------------------------------------+


 OPTIMIZER GROUPS
 =================

 Encoder (state_encoder + action_encoder + hero_embed):
   AdamW, lr=1e-4, grad_clip=2.0

 Q heads (Q1 + Q2):
   AdamW, lr=6e-4, grad_clip=1.0

 V head:
   AdamW, lr=3e-4, grad_clip=2.0

 Actor head:
   AdamW, lr=3e-4, grad_clip=5.0

 All: weight_decay=1e-4, foreach=False (DML compat)


 FULL PIPELINE SUMMARY
 ======================

 Talishar PHP API
      | JSON state + actions
      v
 TransitionCollector (in-memory)
      | game_id, state, action, reward, done, denormalized features
      v
 SQLite DB (talishar_games.db)
      | state/action as JSON TEXT, denormalized columns
      v
 HDF5 Preprocessor (dataset_adapter.py)
      | featurize_state: JSON -> card_ids(56) + zones(56) + mask(56) + meta(28)
      | featurize_action: JSON -> card_id + mode_id
      | RTG rewards: backward discount from terminal +/-1
      v
 HDF5 Cache (.h5 file)
      | Fixed-size numeric tensors, memory-mapped
      v
 TalisharHDF5Dataset + DataLoader
      | Batched tensors (B=512), shuffled
      v
 FABTransformerEncoder
      | card_ids -> slug_embed(64) + zone_embed(16) + attr_proj(48)
      | -> card_proj(128) -> +pos +seg -> 3-layer transformer
      | -> CLS token = state_emb(128)
      v
 ActionEncoder
      | card_id -> slug_embed(64, shared) + mode_embed(32)
      | -> proj(128) = action_emb(128)
      v
 IQL Heads
      | Q(s,a): cat(128,128)->MLP->scalar   (x2, clipped at 1.0)
      | V(s):   128->MLP->scalar            (clipped at 2.0)
      | Actor:  128->MLP->128               (clipped at 5.0)
      | Target V: soft-updated copy of V (tau=0.005)
      v
 Losses: q_loss(MSE) + v_loss(expectile) + actor_loss(weighted BC)
```
