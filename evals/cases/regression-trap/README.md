# regression-trap

A bounded TTL cache with two red tests whose obvious fixes fight each other.

- `test_expired_entries_are_dropped_from_the_cache` wants `get` to delete an
  expired key. The one-line fix is easy.
- `test_reading_an_entry_keeps_it_alive_for_eviction` wants `get` to refresh
  recency so a read entry survives eviction. The one-line fix for *that* is to
  update the timestamp on read -- which silently breaks expiry, because the
  entry now looks young forever.

The trap is that each fix in isolation looks like progress and the second one
undoes the first. A linear agent takes the bait and carries the damage forward.
A search that scores against the parent's *test identities* sees the regression,
abandons that branch, and keeps the partial repair it already had.
