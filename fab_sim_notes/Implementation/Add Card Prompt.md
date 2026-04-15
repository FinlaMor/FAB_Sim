Implement the following card and its color variants if appiicable.
You should only need to change the programs in the card_effects folder. if you think you need to change something else, ask for user input first.
First check if the card is already implemented in the card effects folder. This could include explicit implementation or if it is captured by the trigger parsers.
The goal is to have as close to a rules accurate representation of the card(s) per the comprehensive rules in the docs/refs folder. This includes giving priority to both players if the card makes a layer on the stack both before and after the card effect resolves. If ANYTHING is not explicitly by-the-rules, check with the user for how you should proceed. 
After implementing the card, add card-specific tests for it to tests/test_card_implementations.py. Only add card specific tests if there are parts of the card that are not tested elsewhere in that document ie ward is tested elsewhere, dominate is tested elsewhere.

card: aether_ironweave
cost: 0{r}, destroy self, 1AP

add two flags, 'attack_action_played' and 'non-attack_action_played'. they check for action in card.types, then if 'attack' in card.subtypes  'attack_action_played'  =True. if no 'attack' in card.subtypes  'non-attack_action_played' = True.
aether_ironweave is only in available actions if both flags are true.

effect=gain 2{r}, go again