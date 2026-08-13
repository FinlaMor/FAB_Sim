# become_the_bottle_blue — loadgate — Needs New DSL

**Reason:** load gate failed after retry: ValueError: Unknown DSL effect type: 'GRANT_KEYWORD' (params: {'keyword': 'GO_AGAIN'})

## Raw claw-code output

```
{
  "slug": "become_the_bottle_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ATTACK",
      "effects": [
        {
          "type": "CHOOSE",
          "choose": {
            "type": "CARD",
            "zone": "COMBAT_CHAIN",
            "amount": 1,
            "on_choose": [
              {
                "type": "SET_FLAG",
                "flag": "CHOOSEN_CARD_NAME",
                "value": {
                  "type": "GET_PROPERTY",
                  "target": "CHOICE",
                  "property": "name"
                }
              }
            ]
          }
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "CHOOSEN_CARD_NAME"
        }
      ],
      "effects": [
        {
          "type": "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA",
          "mod": "set",
          "amount": {
            "type": "GET_FLAG",
            "flag": "CHOOSEN_CARD_NAME"
          }
        }
      ]
    },
    {
      "ability_type": "STATIC",
      "effects": [
        {
          "type": "GRANT_KEYWORD",
          "keyword": "GO_AGAIN"
        }
      ]
    }
  ]
}
```
