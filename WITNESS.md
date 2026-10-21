# The witness, and how to stand it up on a second machine

The perceiver cannot report its own absence. Every verdict is emitted by the loop while it runs; if it
stops, the stream stops, and a stopped stream looks exactly like a stream that found nothing.

So the perceiver **pushes** each beat to another machine, and the witness there only has to watch an inbox:

    watch.py ... --push-to user@otherhost:/path/beats.jsonl
    witness_gap.py --stream /path/beats.jsonl --max-age 180 --witness-log /path/witness.jsonl

Push, not pull, on purpose: the watched box needs no sshd, no inbound firewall rule and no credentials
into the thing being watched. A push that fails is the far side seeing nothing — which is the signal.

## Measured, 2026-10-21

    perceiver running   witness: OK    newest beat 6s old (limit 180s) · {'OK': 14}
    perceiver stopped   witness: GAP   the newest beat is 255s old (limit 180s)
    perceiver restarted witness: OK

Both states were exercised on purpose. A witness that has only ever said OK has not been tested.

## Install on the far side (user units, reversible)

    # ~/.config/systemd/user/spine-witness.service   (Type=oneshot, calls witness_gap.py)
    # ~/.config/systemd/user/spine-witness.timer     (OnUnitActiveSec=2min)
    systemctl --user enable --now spine-witness.timer

Exit codes, and they are not interchangeable: 0 the stream is current · 1 the stream has stopped ·
2 the witness could not look (a distinct, failing state — "I could not look" is not "it is fine").
