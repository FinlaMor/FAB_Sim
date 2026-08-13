# assembly_module_blue — loadgate — Needs New DSL

**Reason:** load gate failed after retry: ValueError: Unknown DSL cost type: 'REMOVE_COUNTER' (params: {'counter': 'steam'})

## Raw claw-code output

```
{
  "slug": "assembly_module_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "cost": [
        {
          "type": "REMOVE_COUNTER",
          "counter": "steam"
        }
      ],
      "effects": [
        {
          "type": "DESTROY_PERMANENT",
          "target": "self"
        }
      ]
    },
    {
      "ability_type": "ACTIVATE",
      "activation_cost": 1,
      "effects": [
        {
          "type": "SEARCH_DECK",
          "filter": {
            "card_class": "Hyper Driver"
          },
          "amount": 1,
          "put_into": "arena"
        },
        {
          "type": "SHUFFLE_DECK"
        }
      ]
    }
  ]
}
```
