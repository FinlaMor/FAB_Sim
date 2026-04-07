#!/bin/bash
# Usage: ./implement_card.sh "Card Name Red/Yellow/Blue"
# Usage: ./implement_card.sh "Card Name Red/Yellow/Blue" "extra context or card text here"
#
# Sends the standard card implementation prompt to claude CLI.
# Optionally appends extra card details as a second argument.

if [ -z "$1" ]; then
  echo "Usage: $0 \"Card Name\" [\"extra card text\"]"
  exit 1
fi

CARD="$1"
EXTRA="${2:-}"

TEMPLATE_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$TEMPLATE_DIR/card_prompt_template.txt"

if [ ! -f "$TEMPLATE" ]; then
  echo "Error: template not found at $TEMPLATE"
  exit 1
fi

PROMPT="$(sed "s/__CARD__/$CARD/" "$TEMPLATE")"

if [ -n "$EXTRA" ]; then
  PROMPT="$PROMPT
$EXTRA"
fi

echo "$PROMPT" | claude
