# channel_galcias_cradle_blue — loadgate — Needs New DSL

**Reason:** load gate failed after retry: ValueError: Unknown DSL effect type: 'FREEZE' (params: {'target': 'REF'})

## Raw claw-code output

```
{
  "slug": "channel_galcias_cradle_blue",
  "abilities": [
    {
      "ability_type": "TRIGGERED",
      "trigger": "ON_ENTER_PLAY",
      "effects": [
        {
          "type": "FREEZE",
          "target": "REF"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "START_OF_TURN",
      "effects": [
        {
          "type": "FREEZE",
          "target": "REF"
        }
      ]
    },
    {
      "ability_type": "TRIGGERED",
      "trigger": "END_OF_TURN",
      "effects": [
        {
          "type": "PUT_COUNTER",
          "target": "self",
          "counter": "FLOW"
        },
        {
          "type": "PAY_OR_ELSE",
          "player": "ACTIVE",
          "resources": 0,
          "on_failure": [
            {
              "type": "DESTROY_PERMANENT",
              "target": "self"
            }
          ],
          "on_success": [
            {
              "type": "PUT_CARDS_BOTTOM",
              "target": "player",
              "zone": "PITCH",
              "card_filter": {
                "subtype": "Ice"
              },
              "amount": 1
            }
          ]
        }
      ]
    }
  ]
}
```
