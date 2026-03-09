"""
generate_seed.py — Auto-generate seed_data.sql from the live Python dicts.

Reads CARD_TRIGGERS, EQUIPMENT_ACTIVATION_CONDITIONS, EQUIPMENT_ACTIVATION_COST,
EQUIPMENT_ACTIVATION_EFFECTS, and TURN_ATTACK_EFFECTS directly from the Python
source, then writes correct INSERT statements to seed_data.sql.

Run from FAB_Sim_v2/:
    python -m engine.card_effects.db.generate_seed

Every row is written as 'custom' with the real Python function name. The schema
supports data-driven effect_types (gain_life, draw, etc.) for simple cases, but
since the generator can't always determine intent from a function object, all
rows default to custom. You can hand-edit simple rows to non-custom types after.
"""
from __future__ import annotations

import inspect
import json
import pathlib
import sys
import textwrap

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fn_name(fn) -> str | None:
    """Return the best available name for a callable, or None for lambdas."""
    if fn is None:
        return None
    name = getattr(fn, '__name__', None)
    if name and name != '<lambda>':
        return name
    # Try to get the underlying function from a closure
    if hasattr(fn, '__wrapped__'):
        return _fn_name(fn.__wrapped__)
    # It's a lambda — we can't get a useful name
    return None


def _json(d: dict) -> str:
    return json.dumps(d, separators=(',', ':'))


def _esc(s: str) -> str:
    return s.replace("'", "''") if s else ''


def _val(v) -> str:
    if v is None:
        return 'NULL'
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, int):
        return str(v)
    return f"'{_esc(str(v))}'"


# ---------------------------------------------------------------------------
# Build SQL sections
# ---------------------------------------------------------------------------

def gen_token_keywords() -> list[str]:
    """Token keyword rows — these are stable and hand-authored."""
    return [
        "-- Token keywords",
        "INSERT OR REPLACE INTO token_keywords VALUES ('spectral_shield',  'Ward 1');",
        "INSERT OR REPLACE INTO token_keywords VALUES ('spellbane_aegis',  'Spellvoid 1');",
        "INSERT OR REPLACE INTO token_keywords VALUES ('aether_ashwing',   'Arcane Barrier 1');",
    ]


def gen_card_triggers() -> list[str]:
    from engine.card_effects.triggers import CARD_TRIGGERS, TriggerDef

    lines = ["", "-- ===========================================================================",
             "-- CARD TRIGGERS (auto-generated from CARD_TRIGGERS dict)",
             "-- ==========================================================================="]

    for slug in sorted(CARD_TRIGGERS.keys()):
        trigger_defs = CARD_TRIGGERS[slug]
        lines.append(f"")
        lines.append(f"-- {slug}")
        for priority, tdef in enumerate(trigger_defs):
            event_type = tdef.event_type
            is_optional = 1 if tdef.is_optional else 0

            # Condition
            cond_name = _fn_name(tdef.condition_fn)
            if tdef.condition_fn is None:
                cond_type = 'none'
                cond_params = '{}'
                cond_fn = 'NULL'
            elif cond_name:
                cond_type = 'custom'
                cond_params = '{}'
                cond_fn = f"'{cond_name}'"
            else:
                # Lambda condition — embed source hint in params
                cond_type = 'custom'
                cond_params = '{}'
                try:
                    src = inspect.getsource(tdef.condition_fn).strip()[:120]
                    cond_params = _json({'lambda': src})
                except Exception:
                    pass
                cond_fn = 'NULL'

            # Effect
            eff_name = _fn_name(tdef.effect_fn)
            if eff_name:
                eff_type = 'custom'
                eff_params = '{}'
                eff_fn = f"'{eff_name}'"
            else:
                # Lambda effect
                eff_type = 'custom'
                eff_params = '{}'
                try:
                    src = inspect.getsource(tdef.effect_fn).strip()[:200]
                    eff_params = _json({'lambda': src})
                except Exception:
                    pass
                eff_fn = 'NULL'

            lines.append(
                f"INSERT INTO card_triggers "
                f"(slug, event_type, condition_type, condition_params, condition_fn, "
                f"effect_type, effect_params, effect_fn, is_optional, intra_card_order) VALUES "
                f"('{slug}', '{event_type}', '{cond_type}', '{_esc(_json(json.loads(cond_params)) if cond_params != '{}' else '{}')}', "
                f"{cond_fn}, "
                f"'{eff_type}', '{_esc(eff_params)}', {eff_fn}, {is_optional}, {priority});"
            )

    return lines


def gen_equipment_activations() -> list[str]:
    from engine.card_effects.registry import (
        EQUIPMENT_ACTIVATION_CONDITIONS,
        EQUIPMENT_ACTIVATION_COST,
    )
    # EQUIPMENT_ACTIVATION_EFFECTS may not exist as a module-level dict
    try:
        from engine.card_effects.registry import EQUIPMENT_ACTIVATION_EFFECTS
    except ImportError:
        EQUIPMENT_ACTIVATION_EFFECTS = {}

    lines = ["", "-- ===========================================================================",
             "-- EQUIPMENT ACTIVATIONS (auto-generated)",
             "-- ==========================================================================="]

    all_slugs = sorted(set(
        list(EQUIPMENT_ACTIVATION_CONDITIONS.keys()) +
        list(EQUIPMENT_ACTIVATION_COST.keys()) +
        list(EQUIPMENT_ACTIVATION_EFFECTS.keys())
    ))

    for slug in all_slugs:
        cond_fn = EQUIPMENT_ACTIVATION_CONDITIONS.get(slug)
        cost_val = EQUIPMENT_ACTIVATION_COST.get(slug)
        eff_fn = EQUIPMENT_ACTIVATION_EFFECTS.get(slug)

        # Activation cost
        if cost_val is None:
            act_cost = 'NULL'
            act_cost_fn = 'NULL'
        elif callable(cost_val):
            act_cost = 'NULL'
            fn_name = _fn_name(cost_val)
            act_cost_fn = f"'{fn_name}'" if fn_name else 'NULL'
        else:
            act_cost = str(int(cost_val))
            act_cost_fn = 'NULL'

        # Condition
        if cond_fn is None:
            cond_type = 'none'
            cond_params = '{}'
            cond_fn_val = 'NULL'
        else:
            fn_name = _fn_name(cond_fn)
            if fn_name:
                cond_type = 'custom'
                cond_params = '{}'
                cond_fn_val = f"'{fn_name}'"
            else:
                cond_type = 'custom'
                cond_params = '{}'
                cond_fn_val = 'NULL'

        # Effect
        if eff_fn is None:
            eff_type = 'none'
            eff_fn_val = 'NULL'
        else:
            fn_name = _fn_name(eff_fn)
            eff_type = 'custom'
            eff_fn_val = f"'{fn_name}'" if fn_name else 'NULL'

        lines.append(
            f"INSERT OR REPLACE INTO equipment_activations "
            f"(slug, activation_cost, activation_cost_fn, condition_type, condition_params, "
            f"condition_fn, effect_type, effect_fn) VALUES "
            f"('{slug}', {act_cost}, {act_cost_fn}, '{cond_type}', '{cond_params}', "
            f"{cond_fn_val}, '{eff_type}', {eff_fn_val});"
        )

    return lines


def gen_turn_attack_effects() -> list[str]:
    from engine.card_effects.registry import TURN_ATTACK_EFFECTS

    lines = ["", "-- ===========================================================================",
             "-- TURN ATTACK EFFECTS (auto-generated from TURN_ATTACK_EFFECTS dict)",
             "-- ==========================================================================="]

    for flag, entry in sorted(TURN_ATTACK_EFFECTS.items()):
        cond_fn = entry.get('condition_fn')
        apply_fn = entry.get('apply_fn')

        if cond_fn is None:
            cond_type = 'any'
            cond_params = '{}'
            cond_fn_val = 'NULL'
        else:
            fn_name = _fn_name(cond_fn)
            cond_type = 'custom'
            cond_params = '{}'
            cond_fn_val = f"'{fn_name}'" if fn_name else 'NULL'

        if apply_fn is None:
            eff_type = 'none'
            eff_fn_val = 'NULL'
        else:
            fn_name = _fn_name(apply_fn)
            eff_type = 'custom'
            eff_fn_val = f"'{fn_name}'" if fn_name else 'NULL'

        lines.append(
            f"INSERT OR REPLACE INTO turn_attack_effects "
            f"(flag, condition_type, condition_params, condition_fn, effect_type, effect_fn) VALUES "
            f"('{_esc(flag)}', '{cond_type}', '{cond_params}', {cond_fn_val}, '{eff_type}', {eff_fn_val});"
        )

    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate(out_path: pathlib.Path | None = None) -> None:
    out_path = out_path or (pathlib.Path(__file__).parent / "seed_data.sql")

    sections = [
        ["-- seed_data.sql — AUTO-GENERATED by generate_seed.py",
         "-- DO NOT EDIT BY HAND — run `python -m engine.card_effects.db.generate_seed` to regenerate.",
         "-- Hand-edit only the token_keywords section; all other sections are overwritten on regeneration.",
         ""],
    ]
    sections.append(gen_token_keywords())
    sections.append(gen_card_triggers())
    sections.append(gen_equipment_activations())
    sections.append(gen_turn_attack_effects())

    all_lines = []
    for section in sections:
        all_lines.extend(section)
        all_lines.append("")

    out_path.write_text("\n".join(all_lines), encoding="utf-8")

    # Count rows
    trigger_rows = sum(1 for l in all_lines if l.startswith("INSERT INTO card_triggers"))
    equip_rows = sum(1 for l in all_lines if l.startswith("INSERT OR REPLACE INTO equipment_activations"))
    tae_rows = sum(1 for l in all_lines if l.startswith("INSERT OR REPLACE INTO turn_attack_effects"))
    print(f"Generated {out_path}")
    print(f"  card_triggers:         {trigger_rows} rows")
    print(f"  equipment_activations: {equip_rows} rows")
    print(f"  turn_attack_effects:   {tae_rows} rows")


if __name__ == "__main__":
    generate()
