# Public platform-registry snapshot

This repository is intended to check the public API at
`https://platform.economy.gov.ru/ru` approximately every four hours. The
collector stores only public registry number, platform name, domain, operator,
INN, update date, status, check time, and a bounded change history. It never
stores API credentials or SSH keys.

**Source caveat:** The source page says its current table is illustrative and
does not correspond to actual registry data. Do not use these records as proof
of legal status. The snapshot is for tracking changes to the source page.

The workflow fails without overwriting the last snapshot if the API is
unavailable or returns an invalid/incomplete response. The FNS monitor shows
when its last successful snapshot becomes stale.
