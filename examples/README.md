# Examples

Two receipts from the first build, written from the records as they were made and stripped of
everything specific to the machine they ran on.

## The ledger schema

The first artifact was a SQLite ledger schema with a done-refusal trigger: a loop cannot be
moved to done while the receipts it owes are missing, so the finished state cannot be reached
by editing a status column alone. Around it went a single-file command line client, a
statement-shape guard that classifies every statement a connection is allowed to run, and
scoped connections whose grants come from a table the module itself owns rather than from the
caller, with any scope that would name the verification table refused outright.

Inspection came back with two blockers, each carrying a one-line reproduction rather than a
description. The first was that the connection factory took its grant list as an argument, so
a caller could hand it a scope containing a delete and remove the very verification row the
done-refusal trigger protects; afterward the guard's own proof read zero. The second was that
a byte-order mark at the head of a statement was classified as punctuation, which left the
statement head unreadable and let an unguarded update through. Both were closed, the scope
factory now taking a scope name instead of grants, and the tokenizer skipping the mark the way
the database does. Nineteen regression tests went in, twelve of which fail against the
pre-fix code and pass after it, and the inspection run came back green at 477 tests, with the
receipt re-quoting that same green run twice more after later edits.

## The phone-sized status page

The second artifact was a single-page status view built from the same ledger: static, no
JavaScript, mobile first, a fixed maximum width, regenerated on a schedule, with a print-only
mode for reading a render without publishing it. Inspection came back split. One reviewer
passed it with two minors; the other returned FAIL with five blockers, each with a one-line
reproduction: a queue card printed the payload file's current contents without checking them
against the hash recorded when the card was queued, so an edited file would be shown as the
reviewed one; a long payload was silently truncated; a section that must never ask the human a
question could render question-form text as a step; a blocked row named the age and the reason
but not the client it was holding up; and the print-only path wrote no page but also skipped
the freshness heartbeat, the field that tells the next reader whether the page is alive.

Every blocker was fixed with a named regression test, and the fixes were proved by mutation
rather than by assertion: the fix text was swapped back for the round-one text in a scratch
copy of the tree, the one test that owns it was run, the fix restored, and the test re-run,
with the harness exiting non-zero if a mutation stayed green. Re-inspection was not a
formality. A later round refused a fix from the round before it, a payload reader that turned
out to read from paths the writer never wrote to, and that correction went in with five tests
and five mutations of its own. The page passed re-inspection after that, and the one finding
that was a design question rather than a bug was filed as an open question instead of being
quietly worked around.
