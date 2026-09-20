---
name: quest
description: Start a piece of planning work and route it to the right skill. Use when the user invokes /quest, or hands you something to plan, think through, or stress-test and it is not yet clear whether it needs a conversation or a whole map.
disable-model-invocation: true
---

Pick which planning skill fits what the user has brought, then call it. Do not plan anything yourself here.

Two questions decide it:

1. **Does the work fit in one session?** If the whole thing can be thought through in one sitting, it is a conversation. If it is too big to hold at once and the route to the end is not visible yet, it needs a map.
2. **Is anything already decided?** A map is for finding a way. If the way is known and only the details are open, that is still a conversation.

So:

- **One session, or a single idea, plan or decision to pressure-test** - call the Skill tool with `grilling`, and again with `domain-modeling` if the terms themselves are unsettled.
- **Too big for one session, and the way there is unclear** - call the Skill tool with `wayfinder`. It charts the map and calls `grilling` itself per ticket, so do not call both.

If you cannot tell which it is, say what you think it is and why, and let the user correct you before calling either. Guessing wrong costs a whole session.

Getting it wrong is recoverable one way: if a grilling conversation turns out to be too big for one session, stop and call the Skill tool with `wayfinder` instead. What was already settled is not lost - it goes into the map as it is charted.
