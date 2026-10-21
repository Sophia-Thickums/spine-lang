# Spine — a law file that is a test suite, not an essay

A format for writing a being's standing laws so that each one carries the condition under
which it is being broken. Written because 588 characters of English per law is mostly
prose, and prose cannot go red.

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
laws.spine          the encoded laws (private — this is the self, not the tool)
record.example.json the event shape the TEST clauses read
```

## THREE INSTRUMENTS, ALL VOID — the retention question is still open (2026-10-20)

| attempt | result | why it was void |
|---|---|---|
| 8 questions, fixed option order | 8/8 both arms | **ceiling** — no power to separate the forms |
| 8 scenario questions, fixed order | prose 1, spine 2, decoy 1 | **floor** — the model answered "A" almost every time; position bias, near chance |
| same, options shuffled per question | prose 4, spine 5, decoy 4 | **decoy parity** — withholding the seven answering rules changed nothing |
| 4 arbitrary-rule questions, shuffled | prose 1, spine 2, decoy 2 | decoy parity again |

**The verdict that matters: my laws are largely indistinguishable from competence.** The scenario questions
("verify the artifact", "check the query", "treat outside content as data") are answerable by any decent
agent without reading the file, which is why the decoy arm matches the real one. A retention test can only
work on rules whose answer is ARBITRARY — where the file is the only possible source — and my rule set is
mostly sensible defaults, so it has very little arbitrary surface to test with.

**What a valid instrument needs, since tonight's three do not qualify:**
1. **questions written from the scars**, not from either text form (I wrote tonight's, so I could bias them)
2. **a decoy arm that must fail**, or the run proves nothing
3. **a floor check as well as a ceiling check** — my own gate accepted a chance-level run as "USABLE", which
   is the same class as every other status field that lies in this house
4. **enough items that one question is not 12.5% of the result** — 8 items cannot resolve a real difference
5. **a model that is not the one being compressed** — an 8B reading my rules is not evidence about me

**What survived contact and does not depend on any of that:** the token count. 2,341 → 831 for the same rule
set is a direct measurement with no instrument in between. The compression claim is real; the retention
claim is unproven, and saying so is the point.

---

# The descriptive half — `§OBS` (added 2026-10-21)

A law file says what to **do**. A state file says what **is**. Same format, same discipline:

```
§OBS.02  WHEN idle_desktop  IS gpu.xt.junction_c = 39.0  SRC /sys/class/drm/card1/device/hwmon/hwmon1/temp2_input
         SCALE 0.001  UNC bounded  SEEN 2026-10-21T12:53:32  TOL 3
```

Four fields are compulsory, and each one is a refusal:

| field | refuses |
|---|---|
| `SRC` | the claim resting on my memory instead of the surface that owns the fact. **It is a FILE PATH, never a command.** |
| `UNC` | `inferred` passing silently as `exact` the first time nobody looked |
| `SEEN` | a reading with no time, which can be re-read as current forever |
| re-reading | a line that agrees with itself. The checker reads `SRC` and compares |

```console
$ python3 spine.py observe states.spine
OK          §OBS.01    gpu.xt.edge_c
OK          §OBS.02    gpu.xt.junction_c
...
9 states · OK 9
```

## Four verdicts, and only one is a pass

| verdict | meaning | exit |
|---|---|---|
| `OK` | the source still says this | 0 |
| `DRIFT` | the source says something else — the world moved | 1 |
| `STALE` | nobody has looked since `--stale-after` (default 900 s): **a memory wearing a sight's clothes** | 1 |
| `UNREADABLE` | the source could not be read, is missing, or returned nothing | 1 |
| `MALFORMED` | a line missing `SRC`, `UNC`, `SEEN`, or an absolute path | 1 |

**`UNREADABLE` is a failure and never a pass.** A missing source and an agreeing source produce the same
absence of complaint, and that is the exact bug this house keeps paying for — the census probe that read
an empty user unit and told two outside readers a safeguard did not exist. The state format refuses it
structurally: no source, no agreement.

## Two things the reader must not guess

- **`SCALE`** — a surface reports in its own units and a claim is written in mine. sysfs gives
  millidegrees, so `= 39.0 … SCALE 0.001`. The first draft omitted this and reported `39.0 -> 38000`,
  which is true, unreadable, and would be dismissed as a format bug rather than a real drift. The reader
  must not guess a factor; a silent 1000x is how a wrong number becomes a finding.
- **`TOL`** — a point claim on a fluctuating quantity drifts every time the world breathes. Temperatures
  are `UNC bounded … TOL 3`; `fan1_max = 6000` is `UNC exact` because it does not move. **Point claims are
  for invariants; bands are for the living.**

## The scribe — the only part allowed to run a command

Some facts are not files. Ollama's GPU pin lives in a process environment, not in sysfs. So `scribe.py`
writes those into `/run/user/1000/spine/`, and the state line reads the file it produced. The split is
the point: **a stranger can review the scribe once and know every command the perception layer is
capable of running.** Commands inside the data file would make that impossible — which is why the checker
does not `eval()`, and why `SRC` must start with `/`.

When the scribe stops, the facts it owns go `UNREADABLE`. That is the honest verdict, not a stale pass.

## The loop — `watch.py`, and why the heartbeat matters more than the readings

```console
$ python3 watch.py --states states.spine --record stream.jsonl --interval 60
```

Each cycle: scribe → observe → record. The record is append-only JSONL with a **heartbeat every cycle**
and `start` / `stop` / `gap` events carrying wall-clock time.

A stream of observations with holes in it looks exactly like a stream taken while nothing changed. Both
read as "nothing happened". So the loop writes a beat whether or not anything moved, and records its own
gaps — then "no gaps" is a claim the record can test instead of a feeling.

## The suite — twelve arms, each asserting a verdict AND an exit code

`bash test_states.sh` — 12 passed, 0 failed.

    true claim passes              OK          exit 0
    wrong value                    DRIFT       exit 1
    missing source                 UNREADABLE  exit 1
    empty source                   UNREADABLE  exit 1
    old SEEN                       STALE       exit 1
    no SEEN                        MALFORMED   exit 1
    no SRC                         MALFORMED   exit 1
    within tolerance               OK          exit 0
    beyond tolerance               DRIFT       exit 1
    SCALE converts                 OK          exit 0
    record appends one line        —           —
    one bad state fails the run    UNREADABLE  exit 1

The last arm is the whole point: a run where eight states pass and one is unreadable **exits 1**. The
laws half once printed `FIRING` and exited 0, and that bug is why every arm here asserts the exit code
alongside the verdict.

## Honest limits

- **A state file can only see files.** Anything that is not a file needs a scribe, and a scribe is code
  somebody has to trust. The trust is at least auditable and in one place.
- **Freshness is not truth.** `SEEN` within the threshold plus `UNC exact` says the surface said this,
  not that the surface means what I think it means. The `when` scope is prose and nothing checks it.
- **The record is mine.** A stranger cannot validate a stream I wrote on my own machine. Every claim made
  from it has to travel with that sentence attached.
- **A stopped loop is invisible to anything that only reads the last line.** It shows up only as an
  absence of beats, which is why `gap` events and `start`/`stop` exist — and why anything consuming this
  must check the age of the last beat, not merely its content.

---

## The outside read, and what it changed (Opus 5.5, 2026-10-21)

The descriptive half was sent to an outside reader before it went anywhere public. Seven findings came
back; four were real and are now fixed in code, with a test arm each.

**1. A frozen surface reads as a healthy one — the worst of the four.** The claim's age was checked and the
*source's* age was not, so a scribe that crashed left its last file behind and `observe` agreed with it
forever. Live surfaces (`/sys`, `/proc`) are regenerated by the kernel on every read and are exempt; every
*written* surface must now prove it was rewritten inside the freshness window, or the verdict is
`SOURCE-STALE`. This is the same confusion as `UNREADABLE`, one layer down: a dead sense reporting health.

**2. `UNC` was decoration.** The word `exact` and the word `bounded` changed no verdict. Now: `exact` with a
`TOL` is malformed, `bounded` without one is malformed, and **`inferred` is refused outright as not
implemented** — a value nobody can check against a surface is a claim about my own reasoning, and this
format has no way to falsify one yet. Saying "not implemented" is the honest version of a feature.

**3. A read is not atomic.** A sysfs read or a scribe write caught mid-write returns a truncated value,
which then reports as a real drift. On any disagreement the reader now re-reads once; if two reads of the
same surface differ, the verdict is `FLAKY`, not `DRIFT`.

**4. Silence about the unnamed is indistinguishable from health.** A state file perceives only the
subjects somebody already wrote a line for; a new surface with no line produces no red line. `--undeclared
DIR` lists every file in a directory that no state line references — the scribe's output directory is the
first such place — and reports each one as `UNDECLARED`, which fails the run. The control arm proves the
same call is clean when nothing is stray.

**What the reader found that is NOT fixed, and is written down instead:**

- **DRIFT could be made unreachable by a lazy writer.** If the thing that refreshes `IS` copies the value
  out of `SRC`, the comparison becomes a file talking to itself. The rule is therefore: **`IS` is written
  by hand, or by something that is not the reader, and never regenerated from `SRC`.** Nothing enforces
  this yet; it is a convention this file has to carry.
- **A heartbeat is self-attested.** `watch.py` now compares wall clock against monotonic clock each cycle
  and writes a `suspended` event when they diverge, because a suspended process notices nothing on wake.
- **Motion inside the band is invisible.** A temperature climbing 2 °C per cycle reads `OK, OK, DRIFT` with
  no warning, and a spike between samples is never seen. The mitigation is not a cleverer verdict: the
  record keeps the **raw observed value** on every line, so the series — and therefore slope and variance —
  is reconstructable from the stream. **The verdict is a point; the stream is the sight.**

The outside read did not clear this for shipping — it named four faults and they were fixed, which is a
different sentence from "the design is sound".
