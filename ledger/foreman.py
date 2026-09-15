#!/usr/bin/env python3
"""foreman: the loop ledger CLI. One SQLite file, standard library only."""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "schema.sql")

STATES = ("open", "claimed", "blocked", "needs_you", "done", "killed")
RECEIPT_KINDS = ("brief", "worker_output", "inspection", "verification")
# Exceptions first, then work that nobody has taken, then work in hand.
LIST_ORDER = ("needs_you", "blocked", "open", "claimed")


# ---------------------------------------------------------------- time helpers

def now_iso():
    """Current UTC time as an ISO 8601 string ending in Z."""
    stamp = datetime.now(timezone.utc).replace(microsecond=0)
    return stamp.isoformat().replace("+00:00", "Z")


def parse_time(value):
    """Parse a stored timestamp or date. Return None when it is not a date."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            stamp = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return stamp.replace(tzinfo=timezone.utc)
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def due_moment(raw):
    """The moment a due value turns overdue. A bare date is due at end of day."""
    stamp = parse_time(raw)
    if stamp is None:
        return None
    if len(str(raw).strip()) == 10:
        stamp = stamp.replace(hour=23, minute=59, second=59)
    return stamp


def hours_since(stamp):
    """Whole hours between a stored timestamp and now, or None."""
    moment = parse_time(stamp)
    if moment is None:
        return None
    delta = datetime.now(timezone.utc) - moment
    return int(delta.total_seconds() // 3600)


# ------------------------------------------------------------- output helpers

def short(text, width=52):
    """Trim a long string for a table cell."""
    text = "" if text is None else str(text)
    text = " ".join(text.split())
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def render_table(headers, rows):
    """Plain fixed width table. Returns a string."""
    if not rows:
        return "(no rows)"
    cells = [[("" if c is None else str(c)) for c in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in cells:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)).rstrip()]
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in cells:
        lines.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)).rstrip())
    return "\n".join(lines)


def emit(args, payload, table_text):
    """Print JSON when --json was given, otherwise print the table."""
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print(table_text)


def fail(message, code=1):
    """Print an error and return the exit code for main()."""
    print(message, file=sys.stderr)
    return code


# ------------------------------------------------------------------ db helpers

def db_path_for(args):
    """--db wins, then FOREMAN_DB, then ./foreman.db."""
    if getattr(args, "db", None):
        return args.db
    if os.environ.get("FOREMAN_DB"):
        return os.environ["FOREMAN_DB"]
    return "./foreman.db"


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def get_loop(con, loop_id):
    """Fetch one loop or return None."""
    return con.execute("SELECT * FROM loops WHERE id = ?", (loop_id,)).fetchone()


def require_loop(con, loop_id):
    """Fetch one loop or raise LookupError."""
    loop = get_loop(con, loop_id)
    if loop is None:
        raise LookupError("no loop with id %s" % loop_id)
    return loop


def touch(con, loop_id, **columns):
    """Update columns on a loop and refresh updated_at."""
    columns["updated_at"] = now_iso()
    names = ", ".join("%s = ?" % key for key in columns)
    values = list(columns.values()) + [loop_id]
    con.execute("UPDATE loops SET %s WHERE id = ?" % names, values)


def missing_for_done(con, loop_id):
    """List the artifacts a loop still needs before it can be done."""
    missing = []
    inspection = con.execute(
        "SELECT 1 FROM receipts WHERE loop_id = ? AND kind = 'inspection' AND verdict = 'PASS'",
        (loop_id,),
    ).fetchone()
    if inspection is None:
        missing.append("an inspection receipt with verdict PASS")
    verification = con.execute(
        "SELECT 1 FROM receipts WHERE loop_id = ? AND kind = 'verification'", (loop_id,)
    ).fetchone()
    if verification is None:
        missing.append("a verification receipt")
    return missing


def row_to_dict(row):
    return {key: row[key] for key in row.keys()}


# ------------------------------------------------------------------- commands

def cmd_init(con, args):
    """Create the schema in the target database."""
    if not os.path.exists(SCHEMA_PATH):
        return fail("foreman: schema not found at %s" % SCHEMA_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
        con.executescript(handle.read())
    con.commit()
    print("initialized %s" % db_path_for(args))
    return 0


def cmd_add(con, args):
    """Add a loop in state open."""
    if args.parent is not None and get_loop(con, args.parent) is None:
        return fail("foreman: no parent loop with id %s" % args.parent)
    stamp = now_iso()
    cur = con.execute(
        "INSERT INTO loops (title, owner, state, task_class, created_at, updated_at, due_at, parent_id)"
        " VALUES (?, ?, 'open', ?, ?, ?, ?, ?)",
        (args.title, args.owner, args.task_class, stamp, stamp, args.due, args.parent),
    )
    con.commit()
    loop_id = cur.lastrowid
    if getattr(args, "json", False):
        print(json.dumps(row_to_dict(require_loop(con, loop_id)), indent=2))
    else:
        print("added loop %d: %s" % (loop_id, short(args.title, 72)))
    return 0


def cmd_claim(con, args):
    """Move a loop to claimed and record the owner."""
    try:
        loop = require_loop(con, args.id)
    except LookupError as exc:
        return fail("foreman: %s" % exc)
    if loop["state"] not in ("open", "blocked"):
        return fail(
            "refused: loop %d is %s and cannot be claimed" % (loop["id"], loop["state"])
        )
    touch(con, loop["id"], state="claimed", owner=args.owner)
    con.commit()
    print("loop %d claimed by %s" % (loop["id"], args.owner))
    return 0


def cmd_block(con, args):
    """Move a loop to blocked and record the reason."""
    try:
        loop = require_loop(con, args.id)
    except LookupError as exc:
        return fail("foreman: %s" % exc)
    if loop["state"] in ("done", "killed"):
        return fail("refused: loop %d is %s and cannot be blocked" % (loop["id"], loop["state"]))
    touch(con, loop["id"], state="blocked", notes=args.reason)
    con.commit()
    print("loop %d blocked: %s" % (loop["id"], short(args.reason, 72)))
    return 0


def cmd_ask(con, args):
    """File a decision row and move the loop to needs_you."""
    try:
        loop = require_loop(con, args.id)
    except LookupError as exc:
        return fail("foreman: %s" % exc)
    if loop["state"] in ("done", "killed"):
        return fail("refused: loop %d is %s and cannot ask" % (loop["id"], loop["state"]))
    options = args.options
    cur = con.execute(
        "INSERT INTO decisions (loop_id, question, options, created_at) VALUES (?, ?, ?, ?)",
        (loop["id"], args.question, options, now_iso()),
    )
    touch(con, loop["id"], state="needs_you")
    con.commit()
    print("decision %d filed on loop %d: %s" % (cur.lastrowid, loop["id"], short(args.question, 72)))
    if options:
        print("options: %s" % options)
    return 0


def cmd_decide(con, args):
    """Rule on the oldest open decision row for a loop."""
    try:
        loop = require_loop(con, args.id)
    except LookupError as exc:
        return fail("foreman: %s" % exc)
    row = con.execute(
        "SELECT * FROM decisions WHERE loop_id = ? AND chosen IS NULL ORDER BY id LIMIT 1",
        (loop["id"],),
    ).fetchone()
    if row is None:
        return fail("refused: loop %d has no decision waiting for a ruling" % loop["id"])
    offered = [part.strip() for part in (row["options"] or "").split(",") if part.strip()]
    if offered and args.chosen not in offered:
        return fail(
            "refused: '%s' is not one of the options on decision %d: %s"
            % (args.chosen, row["id"], ", ".join(offered))
        )
    con.execute(
        "UPDATE decisions SET chosen = ?, decided_by = ? WHERE id = ?",
        (args.chosen, args.by, row["id"]),
    )
    # The ruling unblocks the loop. An owner who had claimed it keeps it.
    touch(con, loop["id"], state="claimed" if loop["owner"] else "open", notes=loop["notes"])
    con.commit()
    print(
        "decision %d ruled: %s (by %s). loop %d returns to work"
        % (row["id"], args.chosen, args.by, loop["id"])
    )
    return 0


def cmd_receipt(con, args):
    """File one artifact against a loop."""
    try:
        loop = require_loop(con, args.id)
    except LookupError as exc:
        return fail("foreman: %s" % exc)
    if args.kind not in RECEIPT_KINDS:
        return fail(
            "foreman: kind must be one of %s" % ", ".join(RECEIPT_KINDS)
        )
    verdict = args.verdict.upper() if args.verdict else None
    if verdict is not None and verdict not in ("PASS", "FAIL"):
        return fail("foreman: verdict must be PASS or FAIL")
    cur = con.execute(
        "INSERT INTO receipts (loop_id, kind, path, model, verdict, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (loop["id"], args.kind, args.path, args.model, verdict, now_iso()),
    )
    con.commit()
    print(
        "receipt %d on loop %d: %s%s"
        % (cur.lastrowid, loop["id"], args.kind, " %s" % verdict if verdict else "")
    )
    return 0


def cmd_verify(con, args):
    """Record an independent check. This also files the verification receipt."""
    try:
        loop = require_loop(con, args.id)
    except LookupError as exc:
        return fail("foreman: %s" % exc)
    con.execute(
        "INSERT INTO verifications (loop_id, method, result, evidence_path, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (loop["id"], args.method, args.result, args.evidence, now_iso()),
    )
    result = args.result.strip().upper()
    verdict = result if result in ("PASS", "FAIL") else None
    con.execute(
        "INSERT INTO receipts (loop_id, kind, path, model, verdict, created_at)"
        " VALUES (?, 'verification', ?, NULL, ?, ?)",
        (loop["id"], args.evidence or args.method, verdict, now_iso()),
    )
    con.commit()
    print("loop %d verified by %s: %s" % (loop["id"], args.method, short(args.result, 60)))
    return 0


def cmd_done(con, args):
    """Close a loop. The trigger decides whether the evidence is there."""
    try:
        loop = require_loop(con, args.id)
    except LookupError as exc:
        return fail("foreman: %s" % exc)
    if loop["state"] == "done":
        print("loop %d is already done" % loop["id"])
        return 0
    if loop["state"] == "killed":
        return fail("refused: loop %d was killed and cannot be done" % loop["id"])

    # The trigger decides whether the evidence is present. This guard covers the
    # one case the trigger does not read: the most recent verification returned
    # FAIL, so the loop was fixed but never re-verified. An older FAIL is not a
    # life sentence, because a later PASS replaces it.
    last_verification = con.execute(
        "SELECT verdict FROM receipts WHERE loop_id = ? AND kind = 'verification'"
        " ORDER BY id DESC LIMIT 1",
        (loop["id"],),
    ).fetchone()
    if last_verification is not None and last_verification["verdict"] == "FAIL":
        return fail(
            "refused: the most recent verification of loop %d returned FAIL."
            " Fix the loop and verify it again." % loop["id"]
        )

    missing = missing_for_done(con, loop["id"])
    try:
        con.execute(
            "UPDATE loops SET state = 'done', updated_at = ? WHERE id = ?",
            (now_iso(), loop["id"]),
        )
        con.commit()
    except sqlite3.IntegrityError as exc:
        con.rollback()
        print("REFUSED: %s" % exc, file=sys.stderr)
        if missing:
            print("loop %d is missing %s." % (loop["id"], " and ".join(missing)), file=sys.stderr)
        print(
            "loop %d stays %s. The four artifacts are the brief, the worker output,"
            " the inspector verdicts and the verification." % (loop["id"], loop["state"]),
            file=sys.stderr,
        )
        return 1
    print("loop %d done" % loop["id"])
    return 0


def cmd_kill(con, args):
    """Kill a loop. Killing is a first class end, not a failure."""
    try:
        loop = require_loop(con, args.id)
    except LookupError as exc:
        return fail("foreman: %s" % exc)
    if loop["state"] == "killed":
        print("loop %d is already killed" % loop["id"])
        return 0
    touch(con, loop["id"], state="killed")
    con.commit()
    print("loop %d killed" % loop["id"])
    return 0


def cmd_list(con, args):
    """List loops, exceptions first."""
    clauses = []
    values = []
    if args.state:
        clauses.append("state = ?")
        values.append(args.state)
    if args.owner:
        clauses.append("owner = ?")
        values.append(args.owner)
    if args.task_class:
        clauses.append("task_class = ?")
        values.append(args.task_class)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    order = " CASE state"
    for index, state in enumerate(LIST_ORDER):
        order += " WHEN '%s' THEN %d" % (state, index)
    order += " ELSE %d END, id" % len(LIST_ORDER)
    rows = con.execute("SELECT * FROM loops%s ORDER BY%s" % (where, order), values).fetchall()

    payload = [row_to_dict(row) for row in rows]
    table = render_table(
        ["id", "state", "owner", "class", "due", "updated", "title"],
        [
            [
                row["id"],
                row["state"],
                row["owner"] or "-",
                row["task_class"] or "-",
                row["due_at"] or "-",
                row["updated_at"],
                short(row["title"]),
            ]
            for row in rows
        ],
    )
    if not rows and not getattr(args, "json", False):
        table = "(no loops match)"
    emit(args, payload, table)
    return 0


def cmd_show(con, args):
    """Show one loop with every receipt, verification, decision and dispatch."""
    try:
        loop = require_loop(con, args.id)
    except LookupError as exc:
        return fail("foreman: %s" % exc)
    receipts = con.execute(
        "SELECT * FROM receipts WHERE loop_id = ? ORDER BY id", (loop["id"],)
    ).fetchall()
    verifications = con.execute(
        "SELECT * FROM verifications WHERE loop_id = ? ORDER BY id", (loop["id"],)
    ).fetchall()
    decisions = con.execute(
        "SELECT * FROM decisions WHERE loop_id = ? ORDER BY id", (loop["id"],)
    ).fetchall()
    dispatches = con.execute(
        "SELECT * FROM dispatches WHERE loop_id = ? ORDER BY id", (loop["id"],)
    ).fetchall()

    payload = {
        "loop": row_to_dict(loop),
        "receipts": [row_to_dict(row) for row in receipts],
        "verifications": [row_to_dict(row) for row in verifications],
        "decisions": [row_to_dict(row) for row in decisions],
        "dispatches": [row_to_dict(row) for row in dispatches],
        "missing_for_done": missing_for_done(con, loop["id"]),
    }

    lines = [
        "loop %d  %s" % (loop["id"], loop["title"]),
        "state %s   owner %s   class %s   due %s"
        % (loop["state"], loop["owner"] or "-", loop["task_class"] or "-", loop["due_at"] or "-"),
        "parent %s   created %s   updated %s"
        % (loop["parent_id"] or "-", loop["created_at"], loop["updated_at"]),
    ]
    if loop["notes"]:
        lines.append("notes %s" % loop["notes"])
    lines.append("")
    lines.append("receipts")
    lines.append(
        render_table(
            ["id", "kind", "verdict", "model", "path"],
            [[r["id"], r["kind"], r["verdict"] or "-", r["model"] or "-", r["path"]] for r in receipts],
        )
    )
    lines.append("")
    lines.append("verifications")
    lines.append(
        render_table(
            ["id", "method", "result", "evidence"],
            [[v["id"], v["method"], v["result"], v["evidence_path"] or "-"] for v in verifications],
        )
    )
    lines.append("")
    lines.append("decisions")
    lines.append(
        render_table(
            ["id", "question", "options", "chosen", "by"],
            [
                [d["id"], short(d["question"]), d["options"] or "-", d["chosen"] or "-", d["decided_by"] or "-"]
                for d in decisions
            ],
        )
    )
    lines.append("")
    lines.append("dispatches")
    lines.append(
        render_table(
            ["id", "class", "model", "effort", "ms", "in", "out", "pool", "blockers", "retries", "verdict"],
            [
                [
                    d["id"],
                    d["task_class"] or "-",
                    d["model"],
                    d["effort"] or "-",
                    d["latency_ms"] if d["latency_ms"] is not None else "-",
                    d["tokens_in"] if d["tokens_in"] is not None else "-",
                    d["tokens_out"] if d["tokens_out"] is not None else "-",
                    d["quota_pool"] or "-",
                    d["blockers"],
                    d["retries"],
                    d["verdict"] or "-",
                ]
                for d in dispatches
            ],
        )
    )
    lines.append("")
    blockers = payload["missing_for_done"]
    lines.append(
        "missing for done: %s" % ("; ".join(blockers) if blockers else "nothing")
    )
    emit(args, payload, "\n".join(lines))
    return 0


def cmd_dispatch(con, args):
    """Record one model call against a loop."""
    try:
        loop = require_loop(con, args.id)
    except LookupError as exc:
        return fail("foreman: %s" % exc)
    cur = con.execute(
        "INSERT INTO dispatches (loop_id, task_class, model, effort, latency_ms, tokens_in,"
        " tokens_out, quota_pool, blockers, retries, verdict, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            loop["id"],
            args.task_class,
            args.model,
            args.effort,
            args.latency_ms,
            args.tokens_in,
            args.tokens_out,
            args.pool,
            args.blockers,
            args.retries,
            args.verdict,
            now_iso(),
        ),
    )
    con.commit()
    print(
        "dispatch %d on loop %d: %s in class %s"
        % (cur.lastrowid, loop["id"], args.model, args.task_class)
    )
    return 0


def cmd_scan(con, args):
    """Find work that has stopped moving. Exit 1 when anything is found."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.stale_hours)
    stale = []
    for row in con.execute("SELECT * FROM loops WHERE state = 'claimed' ORDER BY id"):
        age = hours_since(row["updated_at"])
        moment = parse_time(row["updated_at"])
        if moment is not None and moment < cutoff:
            stale.append(
                {
                    "id": row["id"],
                    "owner": row["owner"],
                    "hours_since_progress": age,
                    "title": row["title"],
                }
            )

    overdue = []
    for row in con.execute("SELECT * FROM loops WHERE state = 'open' ORDER BY id"):
        deadline = due_moment(row["due_at"])
        if deadline is not None and deadline < datetime.now(timezone.utc):
            overdue.append(
                {
                    "id": row["id"],
                    "owner": row["owner"],
                    "due_at": row["due_at"],
                    "title": row["title"],
                }
            )

    waiting = [
        {"id": row["id"], "owner": row["owner"], "title": row["title"]}
        for row in con.execute("SELECT * FROM loops WHERE state = 'needs_you' ORDER BY id")
    ]

    payload = {
        "stale_claimed": stale,
        "open_past_due": overdue,
        "needs_you": waiting,
        "stale_hours": args.stale_hours,
        "found": len(stale) + len(overdue) + len(waiting),
    }

    lines = [
        "stale claimed (no progress in %d hours)" % args.stale_hours,
        render_table(
            ["id", "owner", "hours", "title"],
            [[r["id"], r["owner"] or "-", r["hours_since_progress"], short(r["title"])] for r in stale],
        ),
        "",
        "open and past due",
        render_table(
            ["id", "owner", "due", "title"],
            [[r["id"], r["owner"] or "-", r["due_at"], short(r["title"])] for r in overdue],
        ),
        "",
        "needs you",
        render_table(
            ["id", "owner", "title"],
            [[r["id"], r["owner"] or "-", short(r["title"])] for r in waiting],
        ),
        "",
        "%d item(s) need attention" % payload["found"],
    ]
    emit(args, payload, "\n".join(lines))
    return 1 if payload["found"] else 0


def cmd_bakeoff_check(con, args):
    """Find models that hit the blocker threshold in one class. Exit 2 when found."""
    since = datetime.now(timezone.utc) - timedelta(days=args.window_days)
    since_text = since.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    rows = con.execute(
        "SELECT model, SUM(blockers) AS blockers, COUNT(*) AS dispatches,"
        " SUM(retries) AS retries, MAX(quota_pool) AS pool"
        " FROM dispatches WHERE task_class = ? AND created_at >= ?"
        " GROUP BY model HAVING SUM(blockers) >= 3 ORDER BY blockers DESC, model",
        (args.task_class, since_text),
    ).fetchall()

    payload = {
        "task_class": args.task_class,
        "window_days": args.window_days,
        "since": since_text,
        "threshold": 3,
        "triggered": [row_to_dict(row) for row in rows],
    }

    lines = [
        "bake-off check: class %s, last %d days, since %s" % (args.task_class, args.window_days, since_text),
        render_table(
            ["model", "blockers", "dispatches", "retries", "pool"],
            [
                [r["model"], r["blockers"], r["dispatches"], r["retries"], r["pool"] or "-"]
                for r in rows
            ],
        ),
    ]
    if rows:
        lines.append("")
        lines.append("Run a bake-off for these models: see doctrine/bakeoff.md.")
    emit(args, payload, "\n".join(lines))
    return 2 if rows else 0


# ----------------------------------------------------------------------- main

def build_parser():
    # SUPPRESS keeps the subparser default from overwriting a --db given before
    # the subcommand, so --db works in either position.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--db",
        default=argparse.SUPPRESS,
        help="path to the ledger file (default: $FOREMAN_DB, then ./foreman.db)",
    )

    parser = argparse.ArgumentParser(
        prog="foreman",
        description="The loop ledger. Loops, receipts, verifications, decisions, dispatches.",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, handler, help_text, with_json=False):
        child = sub.add_parser(name, help=help_text, parents=[common])
        if with_json:
            child.add_argument("--json", action="store_true", help="print JSON instead of a table")
        child.set_defaults(handler=handler)
        return child

    add("init", cmd_init, "create the ledger and its schema")

    p = add("add", cmd_add, "add a loop", with_json=True)
    p.add_argument("title", help="one line stating the work")
    p.add_argument("--owner", help="lane or person accountable")
    p.add_argument("--class", dest="task_class", help="lane key from templates/routing.yaml")
    p.add_argument("--due", help="due date, YYYY-MM-DD or ISO 8601")
    p.add_argument("--parent", type=int, help="parent loop id")

    p = add("claim", cmd_claim, "claim a loop for an owner")
    p.add_argument("id", type=int)
    p.add_argument("--owner", required=True)

    p = add("block", cmd_block, "mark a loop blocked")
    p.add_argument("id", type=int)
    p.add_argument("--reason", required=True)

    p = add("ask", cmd_ask, "file a decision row and set the loop to needs_you")
    p.add_argument("id", type=int)
    p.add_argument("question")
    p.add_argument("--options", required=True, help="comma separated choices")

    p = add("decide", cmd_decide, "rule on the open decision for a loop")
    p.add_argument("id", type=int)
    p.add_argument("--chosen", required=True)
    p.add_argument("--by", required=True)

    p = add("receipt", cmd_receipt, "file an artifact against a loop")
    p.add_argument("id", type=int)
    p.add_argument("--kind", required=True, help="one of: %s" % ", ".join(RECEIPT_KINDS))
    p.add_argument("--path", required=True)
    p.add_argument("--model")
    p.add_argument("--verdict", help="PASS or FAIL, for inspections")

    p = add("verify", cmd_verify, "record an independent check of a loop")
    p.add_argument("id", type=int)
    p.add_argument("--method", required=True)
    p.add_argument("--result", required=True)
    p.add_argument("--evidence")

    p = add("done", cmd_done, "close a loop, if the evidence is there")
    p.add_argument("id", type=int)

    p = add("kill", cmd_kill, "kill a loop")
    p.add_argument("id", type=int)

    p = add("list", cmd_list, "list loops, exceptions first", with_json=True)
    p.add_argument("--state", choices=STATES)
    p.add_argument("--owner")
    p.add_argument("--class", dest="task_class")

    p = add("show", cmd_show, "show one loop and everything filed against it", with_json=True)
    p.add_argument("id", type=int)

    p = add("dispatch", cmd_dispatch, "record one model call against a loop")
    p.add_argument("id", type=int)
    p.add_argument("--model", required=True)
    p.add_argument("--class", dest="task_class", required=True)
    p.add_argument("--effort")
    p.add_argument("--latency-ms", dest="latency_ms", type=int)
    p.add_argument("--tokens-in", dest="tokens_in", type=int)
    p.add_argument("--tokens-out", dest="tokens_out", type=int)
    p.add_argument("--pool")
    p.add_argument("--blockers", type=int, default=0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--verdict")

    p = add("scan", cmd_scan, "find work that has stopped moving", with_json=True)
    p.add_argument("--stale-hours", dest="stale_hours", type=int, default=24)

    p = add("bakeoff-check", cmd_bakeoff_check, "find models past the blocker threshold", with_json=True)
    p.add_argument("--class", dest="task_class", required=True)
    p.add_argument("--window-days", dest="window_days", type=int, default=7)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    path = db_path_for(args)
    if args.command != "init" and not os.path.exists(path) and path != ":memory:":
        return fail(
            "foreman: no ledger at %s. Run: python3 ledger/foreman.py --db %s init" % (path, path)
        )
    try:
        con = connect(path)
    except sqlite3.Error as exc:
        return fail("foreman: cannot open %s: %s" % (path, exc))
    try:
        return args.handler(con, args)
    except sqlite3.Error as exc:
        con.rollback()
        return fail("foreman: %s" % exc)
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
