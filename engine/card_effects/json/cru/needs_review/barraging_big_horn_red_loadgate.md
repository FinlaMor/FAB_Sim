# barraging_big_horn_red — loadgate — Needs New DSL

**Reason:** empty abilities but card has non-keyword text (implementer punted on the effect)

## Raw claw-code output

```
{
  "slug": "barraging_big_horn_red",
  "abilities": [
    {
      "ability_type": "PLAY",
      "additional_cost": [
        {
          "type": "DISCARD_RANDOM"
        }
      ],
      "effects": []
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "DEFENDS_WITH_OTHER_HAND_CARD",
          "amount": 2,
          "mod": "lt"
        }
      ],
      "effects": [
        {
          "type": "GRANT_NEXT_ATTACK_KEYWORD",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
