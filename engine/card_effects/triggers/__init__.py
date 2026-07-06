# triggers package — keyword-trigger infrastructure only.
# Card-specific effects live in the JSON DSL (engine/card_effects/json/).
from engine.card_effects.triggers.triggers import (  # noqa: F401
    CARD_TRIGGERS,
    MELD_EFFECT_REGISTRY,
    TriggerDef,
    build_keyword_triggers,
    get_triggers_for_card,
    register_all_triggers,
    register_card_triggers,
    register_hero_triggers,
)
