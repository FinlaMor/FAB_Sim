# aggressive_pounce_red — loadgate — Needs New DSL

**Reason:** load gate failed after retry: ValueError: Unknown DSL effect type: 'GRANT_KEYWORD' (params: {'keyword': 'GoAgain'})

## Raw claw-code output

```
{
  "slug": "aggressive_pounce_red",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "boosted_this_turn"
        }
      ],
      "effects": [
        {
          "type": "GRANT_KEYWORD",
          "keyword": "GoAgain"
        }
      ]
    }
  ]
}
```
