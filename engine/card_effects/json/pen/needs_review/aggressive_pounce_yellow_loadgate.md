# aggressive_pounce_yellow — loadgate — Needs New DSL

**Reason:** load gate failed after retry: ValueError: Unknown DSL effect type: 'GRANT_KEYWORD' (params: {'keyword': 'GoAgain'})

## Raw claw-code output

```
{
  "slug": "aggressive_pounce_yellow",
  "abilities": [
    {
      "ability_type": "STATIC",
      "conditions": [
        {
          "type": "FLAG_SET",
          "flag": "HAVE_INTIMIDATED_OPPONENT"
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
