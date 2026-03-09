 1. finish game engine implementation for 4 decks: kayo ✓, Mario, oscillio, marlynn
 
     check card effects for accuracy

     update agent prompts to add context for what the decision is
        

 2. run games with random agents and save results to database. need winning data for each hero so 70% mirror matches, 30% vs other decks.

     In parallel, create encoding transformer for ask_agent inputs (state, options) with attention for the priority players' cards in hand, public cards for all players, and (unordered) cards in deck.

 3. run an initial iql training with each deck to see if it beats a random agent of each opponent. 