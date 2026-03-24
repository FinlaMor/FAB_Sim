# IQL Monitoring Cheat Sheet

Current hyperparameters:
```
reward_scale=5.0   expectile=0.9  temperature=0.5  max_weight=100.0
weight_decay=1e-4   lr_encoder=1e-4  lr_q/v/actor=3e-4  gamma=0.97
normalize_advantages=True
```

Log line format:
```
[iql] step=  100 q=0.1234 v=0.0567 actor=0.0890 adv=+0.0012±0.3456 w=1.23 w_max=4.5
```

---

## q (q_loss) -- MSE between Q(s,a) and r + gamma * V_target(s')

**Healthy:** 0.01 -- 1.0 after warmup (first 1k steps can be 5--50+, that is fine). Should trend downward over the run and stabilize. With reward_scale=100 the target values are in [0, ~100], so early q_loss of 100+ is expected.

**Bad -- rising or stuck above 10 after 5k steps:** Q network is not fitting the Bellman targets. Likely causes: lr_q too low, hidden_dim too small, or data is too noisy/sparse.
- Raise `lr_q` from 3e-4 to 1e-3
- Increase `hidden_dim` from 256 to 512

**Bad -- drops to near 0 (<0.001) and stays there:** Q network memorized the dataset; overfitting. Will produce overconfident advantages that break actor training.
- Raise `weight_decay` from 1e-4 to 1e-3
- Lower `lr_q` from 3e-4 to 1e-4
- Collect more games before the next training run

**Bad -- spikes or oscillates wildly (swings of 10x between log intervals):** Gradient instability.
- Lower `lr_q` from 3e-4 to 1e-4
- Lower `grad_clip` from 10.0 to 1.0
- Lower `reward_scale` from 100.0 to 10.0 (reduces target magnitude)

---

## v (v_loss) -- Expectile regression: weight * (Q_min(s,a) - V(s))^2

**Healthy:** 0.001 -- 0.5 once converged. With expectile=0.5 this is symmetric MSE, so v_loss tracks q_loss direction but is typically smaller (V fits a scalar per state, Q fits per state-action).

**Bad -- v_loss >> q_loss (more than 10x):** V network cannot keep up with Q estimates. The advantage signal (Q - V) will be biased upward, inflating weights.
- Raise `lr_v` from 3e-4 to 1e-3
- If persistent, raise `expectile` from 0.5 to 0.7 (makes V track high-Q actions more aggressively, reducing the gap)

**Bad -- v_loss near 0 but q_loss is still high:** V is fitting to garbage Q values. Not dangerous on its own, but means the advantage signal is meaningless. Fix q_loss first.

**Bad -- v_loss oscillating independently of q_loss:** V and Q are not co-adapting properly.
- Synchronize learning rates: set `lr_v = lr_q`
- Lower `tau` from 0.005 to 0.001 (slower target updates = more stable V targets)

---

## actor (actor_loss) -- Advantage-weighted MSE: mean(w_i * ||actor(s) - a_i||^2)

**Healthy:** 0.01 -- 5.0. Depends heavily on embedding dimension (d_model=128 means 128-dim vectors, so per-dim error ~0.0001--0.04 is reasonable). Should decrease over the run, though noisier than q/v because of stochastic weights.

**Bad -- stuck at a high value and not decreasing:** Actor is ignoring the advantage signal; all weights are near-uniform so it is doing unweighted behavior cloning of a random policy. Check w_mean and w_max below.
- Raise `temperature` from 3.0 to 10.0 (sharpens the weight distribution)
- Raise `max_weight` from 50.0 to 100.0 (allows more contrast)
- If adv_std is near 0, the problem is upstream -- fix Q/V first

**Bad -- actor_loss drops fast then climbs back up:** Early overfitting followed by weight distribution shift. Common when dataset is small (<5k transitions).
- Lower `lr_actor` from 3e-4 to 1e-4
- Raise `weight_decay` from 1e-4 to 1e-3
- Collect more games

**Bad -- actor_loss is NaN or inf:** Exploding weights from exp(temperature * advantage).
- Lower `temperature` from 3.0 to 1.0
- Lower `max_weight` from 50.0 to 10.0
- Check w_max -- if it was already at max_weight, lower max_weight further

---

## adv (raw_adv_mean) -- Mean of Q_min(s,a) - V(s) before normalization

**Healthy:** Near 0 and stable (between -1.0 and +1.0 with reward_scale=100). The sign does not matter much because normalization centers it; what matters is stability.

**Bad -- large positive (>5.0) and growing:** Q is overestimating relative to V. Classic offline RL overestimation.
- Raise `expectile` from 0.5 to 0.7 (V tracks higher quantile of Q, closing the gap)
- Lower `reward_scale` from 100.0 to 10.0
- If eval_q_loss >> train q_loss, this confirms Q overfit

**Bad -- large negative (<-5.0):** V is higher than Q. Unusual. Means V overestimates or Q underestimates.
- Lower `expectile` from 0.5 to 0.3 (V tracks lower quantile, bringing it down)
- Check that reward assignment is correct (wins = +1, losses = -1 before scaling)

**Bad -- drifting steadily in one direction over the run:** Non-stationarity in the Bellman targets.
- Lower `tau` from 0.005 to 0.001 (slower target network updates)
- Lower `lr_q` and `lr_v` together by 3x

---

## adv_std (raw_adv_std) -- Std of Q_min(s,a) - V(s) before normalization

**Healthy:** 0.1 -- 10.0 (with reward_scale=100). Should be nonzero and stable. This is the denominator of advantage normalization, so it directly controls weight spread.

**Bad -- near 0 (<0.01):** All advantages are identical; normalization divides by ~0, producing huge or random normalized values. The actor cannot distinguish good from bad actions.
- Raise `reward_scale` from 100.0 to 500.0 (increases signal magnitude)
- Raise `expectile` from 0.5 to 0.7 (V no longer tracks the mean, creating spread)
- Check that Q is actually learning (q_loss should be decreasing)

**Bad -- very large (>50.0) and growing:** Advantage distribution is blowing up. Usually follows Q overestimation.
- Lower `reward_scale` from 100.0 to 10.0
- Lower `lr_q` from 3e-4 to 1e-4
- Raise `weight_decay` from 1e-4 to 1e-3

---

## w (w_mean) -- Mean of exp(temperature * normalized_advantage), clamped to max_weight

**Healthy:** 1.0 -- 5.0. A w_mean of 1.0 means uniform weighting (equivalent to behavior cloning). A w_mean of 3--5 means the actor is meaningfully upweighting good actions.

**Bad -- stuck at 1.0 (or within 0.9--1.1) throughout the run:** Advantage normalization + temperature is not producing differentiation. The actor is doing pure behavior cloning of random policy data.
- Raise `temperature` from 3.0 to 10.0
- If adv_std is near 0, fix the upstream Q/V problem first
- If adv_std is healthy, temperature is just too low

**Bad -- w_mean > 10:** Too many transitions are getting extreme weights. The actor over-fits to a small subset of "winning" actions.
- Lower `temperature` from 3.0 to 1.0
- Lower `max_weight` from 50.0 to 20.0

**Bad -- w_mean dropping toward 0:** Normalized advantages are all very negative. Should not happen with proper normalization (mean is subtracted). Indicates a bug or NaN in the advantage computation.
- Check for NaN in other metrics
- Restart training from the previous checkpoint

---

## w_max -- Max of exp(temperature * normalized_advantage), clamped to max_weight

**Healthy:** 5.0 -- 30.0. Should be higher than w_mean but not pinned at max_weight.

**Bad -- pinned at max_weight (50.0) for many consecutive log intervals:** Too many transitions are hitting the clamp. The advantage distribution has heavy tails, and the clamp is not soft enough.
- Lower `temperature` from 3.0 to 1.0 (first choice -- reduces tail)
- Lower `max_weight` from 50.0 to 20.0 (harder clamp, but narrower effective range)
- Both together if w_max has been pinned since the start

**Bad -- w_max equals w_mean (both ~1.0):** No differentiation at all. Same diagnosis as w_mean stuck at 1.0 above.

**Bad -- w_max is inf or NaN:** exp overflow before the clamp can catch it. This means temperature * normalized_advantage > 88 (float32 exp overflow).
- Lower `temperature` from 3.0 to 1.0 immediately
- Lower `max_weight` from 50.0 to 10.0 as a safety net
- Check adv_std -- if it is near 0, normalization divided by epsilon, producing huge normalized values

---

## PLAYER_BOT_WIN_RATE (Tier 1: benchmark vs random, 20 games)

Acceptance rule: `win_rate > max(0.50, previous_best) + 0.02`

| Win Rate | Meaning | Action |
|----------|---------|--------|
| < 0.45 | Worse than coin flip against random. Model learned nothing or learned wrong policy. | Check actor_loss trend. If actor_loss decreased but win rate is bad, the model overfit to bad data. Collect more games with heuristic bot opponents. |
| 0.45 -- 0.55 | Noise range. Indistinguishable from random with 20 games. | Check Tier 2 (vs heuristic) — if that also fails, need more training data or higher temperature. |
| 0.55 -- 0.75 | Bot is learning. Measurably better than random. | Keep the current hyperparameters. Continue the collect-train-bench loop. |
| > 0.75 | Dominant over random. Random is no longer a useful signal. | Focus on Tier 2 (vs heuristic) as the primary metric. |

---

## PLAYER_BOT_VS_HEURISTIC_WIN_RATE (Tier 2: benchmark vs heuristic bot, 50 games)

Acceptance rule: `win_rate > 0.52` (i.e., 0.50 + margin of 0.02)

The heuristic bot plays highest-power attacks, pitches blue cards first, and blocks with equipment before hand cards. Beating it means the model has learned strategic play beyond "attack with big numbers."

| Win Rate | Meaning | Action |
|----------|---------|--------|
| < 0.35 | Significantly worse than heuristic. Model is not attacking or blocking effectively. | Check per-hero breakdown. Some heroes may lack attack cards in their pool. Ensure training data includes heuristic-bot games (opponent mix). |
| 0.35 -- 0.50 | Competitive but losing. Model has learned some strategy but not enough. | Normal early-training regime. Keep iterating. More heuristic-bot games in training data will help. |
| 0.50 -- 0.60 | Beating the heuristic bot. Model has real strategic understanding. | Strong signal. Consider self-play data collection for harder opponents. |
| > 0.60 | Dominant over heuristic. Ready for self-play progression. | Start collecting bot-vs-bot (self-play) games. Current pipeline does this when an accepted checkpoint exists. |

---

## Per-hero win rate vs dataset win rate

The benchmark reports per-hero win rates alongside each hero's dataset win rate (from talishar_games.db). The **Delta** column shows `bot_wr - dataset_wr`.

| Delta | Meaning | Action |
|-------|---------|--------|
| > +0.10 | Bot plays this hero much better than dataset average. | Hero's strategy is well-captured. Use as positive signal. |
| -0.05 to +0.10 | In line with dataset. | Normal. No action needed. |
| < -0.10 | Bot underperforms this hero vs dataset average. | Check if training data has enough games for this hero. May need targeted data collection. |

---

## PLAYER_BOT_VS_PREV_WIN_RATE (benchmark vs previous best checkpoint)

Acceptance rule: `win_rate > 0.52` (i.e., 0.50 + margin of 0.02)

| Win Rate | Meaning | Action |
|----------|---------|--------|
| < 0.45 | New checkpoint is worse than previous. Regression. | Reject. Investigate: did training overfit? Did the data distribution shift? |
| 0.45 -- 0.52 | No measurable improvement. | Reject (does not clear margin). Acceptable plateau if vs-heuristic rate is already high. Continue collecting data. |
| 0.52 -- 0.60 | Marginal improvement. | Accept. This is the normal regime for incremental gains. |
| > 0.60 | Large jump. Suspicious with small benchmark sample. | Accept, but verify by running a second benchmark with a different seed. |

---

## Quick Decision Tree

```
Is q_loss > 10 after 5k steps?
  YES --> raise lr_q to 1e-3, or increase hidden_dim
  NO  --> continue

Is adv_std < 0.01?
  YES --> raise reward_scale to 500, raise expectile to 0.7
  NO  --> continue

Is w_mean stuck near 1.0?
  YES --> raise temperature to 10.0
  NO  --> continue

Is w_max pinned at max_weight?
  YES --> lower temperature to 1.0
  NO  --> continue

Is actor_loss not decreasing?
  YES --> if w_mean ~1.0: fix weights first (above)
          if w_mean > 1: lower lr_actor to 1e-4, raise weight_decay to 1e-3
  NO  --> training is healthy, check benchmarks

Is win_rate vs random < 0.50?
  YES --> need more data (collect 500+ more games) with heuristic bot opponents
  NO  --> check win_rate vs heuristic

Is win_rate vs heuristic < 0.50?
  YES --> model needs more strategic training data (heuristic + self-play games)
  NO  --> keep iterating, consider self-play data collection
```
