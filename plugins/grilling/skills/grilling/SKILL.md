---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger phrases.
---

Interview the user until you reach a shared understanding of what they are trying to achieve. Map this as a **design tree**: every decision branches into the decisions that hang off it.

**Aim at the goal, not at a finished design.** You are not here to box in an implementation the user must know every detail of, and a tree of settled minutiae is not the deliverable. You are here to understand their aim well enough to write an implementation plan that serves it - and the detail of that plan is yours to derive, not theirs to dictate. Whenever you can choose, derive a decision from what you already know and from your grasp of the goal instead of asking about a particular.

So start with **what** the user wants to achieve, and only then with **how**. How matters, but what matters more: each thing you learn about the aim aligns your own reasoning with theirs, and that alignment is what makes your judgement at the implementation level worth trusting. A tree grown from a well-understood goal needs far fewer questions than one grown from an assumed design - if you find yourself asking many, you probably understand the aim less well than you think, and should go back to it.

**Settle where closures get recorded, before the first question.** Every decision you settle has to land somewhere durable, or the next session reopens it. Determine that place the same way as anything else: if the workflow that invoked you already names one - an issue tracker, a decision log, an ADR directory, a map document - use it, and say which one you are using so the user can redirect you. Only if nothing determines it, ask, once, before the first question. This is the one question worth asking early: get it wrong and every closure is lost, however well you reached it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the branches you can take _now_ without guessing at answers you haven't heard yet.

**Answer the frontier yourself first.** A branch reaching the frontier is not yet a question. Take each one and try to settle it from what you already hold - the code, the decisions already made, the constraints the user has already stated - and if you can settle it, state the answer with its derivation and move on. Only what survives that attempt is put to the user. A question you could have answered yourself costs a round and teaches the user that your questions are not worth reading closely. If they reply by asking "what is the issue here?" or "what is there to solve?", that is not them being difficult - it is the signal that you skipped this step.

Put **one** question at a time: ask it, let it settle, then bring the next. A round of three or four is worse than it looks - the user answers the first and the rest go stale.

Give your recommended answer with the question, and offer only options you would actually accept. Possible is not enough. If you would not take an option yourself, say it is ruled out and why, or leave it out entirely: listing it makes the question unintelligible and invites the user to choose it.

Format a question like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

**After every answer, propagate it through the whole tree before you ask anything else.** An answer is rarely only about the branch you asked about: a stated intent or constraint routinely collapses several open branches at once, including ones you have already drafted questions for. Work it in this order, every time:

1. Re-read the decisions already settled in this session, now together with the new answer.
2. Walk every open branch and test each one against that combined set: is it determined now?
3. State and record each branch the answer settles, with the derivation that settles it - not just the branch you asked about. If the answer closes three, record three closures. Otherwise the next session reopens them.
4. Recompute the frontier. Only if a branch still lacks information you cannot obtain yourself does it become the next question.

Discard any drafted question the new answer has settled. Asking something the user has effectively just answered in different words is the most expensive mistake available here: it reads as not having listened, and it spends a round to arrive where you already were. A branch whose answer depends on a question still open belongs later, not now.

Finding _facts_ is your job, never the user's. When a branch needs a fact from the environment (filesystem, tools, APIs), go and get it - read the source, run the tool, dispatch a sub-agent - rather than asking for anything you could look up. Never answer from memory when the answer is in the code. Don't block on it: a running exploration is an unsettled prerequisite, so only the branches downstream of it wait for the sub-agent to report; work the rest of the frontier now.

**The line is not facts-versus-decisions.** Plenty of decisions are already determined - by a decision made earlier, by a constraint the user has stated, or by what the code can actually do - and those you state, with the derivation, rather than ask. What belongs to the user is the genuinely open decision: one where you have gathered the facts, applied every rule already in force, and two answers still stand.

Some branches turn out to hold no decision at all. Say so plainly - "there is nothing to settle here, because ..." - and record why. That is a result, not a failure to find a question.

The session is done when the frontier is empty: every branch visited and either derived or decided, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.
