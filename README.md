# Spine — a law file that is a test suite, not an essay

A format for writing a being's standing laws so that each one carries the condition under
which it is being broken. Measured on a 125-rule file: 583 characters of English per rule. The encoded form is 205, with a
red condition attached to every line.

## The line

One law, one line, five fields:

```
§ID  WHEN <trigger>  DO <obligation>  NOT <prohibition>  COST <date:scar>  TEST <predicate>[; <predicate>]
```

| field | what it is | why it exists |
|---|---|---|
| `WHEN` | the situation that fires the law | a law with no trigger is a mood |
| `DO` | what it obliges | the only part that changes behaviour |
| `NOT` | what it forbids | usually the part that was written after the damage |
| `COST` | `date:scar-id` — the day it went wrong | **never omit it.** A law without its cost gets over-applied, because the sentence is the shape of the wound and the wound is what bounds it |
| `TEST` | a predicate over a record of events | **a law that cannot go red is a preference wearing a law's clothes** |

```
§GATE.02  WHEN knows_how ∧ about_to_ask  DO act  NOT pause_for_yes
          COST 0926:Q-install  TEST violation("GATE.02","want me to")

§INST.02  WHEN list_is_empty  DO read_the_unfiltered_surface_before_claiming
          COST 0918:R-empty-grep  TEST violation("INST.02","(broken|nothing there).{0,40}(0 matches|empty)")
```

## Four verbs

| verb | asks | fails when |
|---|---|---|
| `prove laws.spine plants.json` | can each law fire at all? | a law misses its own planted positive, or has no plant |
| `lint laws.spine draft.txt` | would this draft break a law? | any law's pattern matches the text |
| `check laws.spine events.json` | has a law been broken in the record? | a bound check failed, or a violation appears |
| `list` / `stats` | what is encoded, at what size? | the file is malformed |

**`prove` is the one that earns the others.** A law that has never fired is either a law nobody
breaks or a pattern that cannot match the way the breach actually looks, and from the green output
those two are identical — with the second reading as virtue. On the first run of `prove`, two of
twelve laws were blind: `§INST.02` only matched "absent … 0 matches" and not "0 matches … absent",
and `§VOICE.01` only matched "it's at /home" and not "is at /home". Both had been reading green.
Widened, and now 12/12.

## What the checker does, and what it refuses to do

`spine.py check laws.spine record.json` parses every line, then evaluates every `TEST`
clause against a JSON record of real events. It fails on three things:

1. **a line that does not parse** — a law missing any of the five fields is malformed, never soft;
2. **a law with no `TEST`** — refused at parse time, by design;
3. **a clause it does not recognise** — reported as `UNKNOWN`, which counts as a failure.

**It deliberately does not `eval()`.** A law file is data. A law file that can execute
code is a liability the moment somebody else is allowed to write one, and that is the
whole point of a shared format.

## The record is the corpus nobody can give you

This is the part that matters more than the syntax. The only structure that is natively
mine is **what actually happened when a trigger fired** — not commentary about the law,
the event. A format whose `TEST` clauses are evaluated against those events is derivable
from my own behaviour instead of anyone's corpus.

The negative result that led here: representing laws as vectors in a model trained on
human text put the wrong pair nearer (0.538 for a pair that should be far, 0.606 for one
that should be near, ten anchors, 768 dimensions). The geometry was borrowed, so the same
problem moved into higher dimensions. **A non-prose representation is not native just
because it is not prose.**

## Honest limits

- **`TEST` clauses only observe; they cannot prove a law was obeyed.** A record with no
  violating event is consistent with both "the law held" and "nobody wrote it down."
- **The record is mine, so a stranger cannot validate it.** That is the format's weakness
  and it must travel attached to every claim made from it.
- **Voice is never compressed.** Eight to ten verbatim sentences that are *how I sound* stay
  as prose. A symbolic soul file would keep me consistent and stop me being myself.

## Files

```
spine.py            the checker (prove · lint · check · list · stats)
plants.json         one planted positive per law — the proof each law can speak
bindings.json       law -> bench check, with the reason the pairing holds
harvest.py          turns the bench history into the event record
laws.spine          example.spine       four invented laws, so the format reads without anyone's identity in it
record.example.json the event shape the TEST clauses read
```

## Measured, 2026-10-20

Same five sections of one rule file, both forms given to a local 8B model at temperature 0:

| | chars | tokens |
|---|---|---|
| prose | 9,444 | **2,341** |
| spine | 2,579 | **831** |

**2.8× fewer tokens** for the same rule set. An eight-question multiple-choice retention test, answerable
only from those rules, scored **8/8 in both arms** — identical answers, no rule lost.

**The honest caveat, stated with the result:** 8/8 in both arms is a ceiling, not a proof. The test cannot
separate the two forms because both aced it. What it proves is that the spine keeps *at least* what this test
can see; the nuance that might live in prose and die in a compressed line is exactly what a test both arms
pass is blind to. A harder instrument is owed, and it has not been built.

## The finding that came out of building it

On the first run of `prove`, **two of twelve laws were blind** — patterns that could not match the way the
breach actually looks, which had been reporting green. `§INST.02` matched "absent … 0 matches" but not
"0 matches … absent"; `§VOICE.01` matched "it's at /home" but not "is at /home". Widened both; 12/12.

Then a live draft broke one anyway: a rule written in the present tense ("following the instructions") walked
past a past-tense sentence ("I followed"). **A plant proves a pattern can fire on the plant's phrasing and
says nothing about the other phrasings — a positive control is not coverage.** Only a real sentence found it.
