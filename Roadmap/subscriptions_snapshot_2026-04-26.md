# Subscriptions Snapshot — 26 April 2026

**Purpose:** Preserve curated subscription list ahead of any future redesign of the Subscriptions feature (Enhancement 5 completion + tree-structure rework). To be used as a reference for re-populating subscriptions if/when the migration path requires re-entry rather than auto-import.

**Source:** `%APPDATA%\DocAnalyser_Beta\subscriptions.json` (live snapshot at 2026-04-26 ~16:30)

**Total subscriptions:** 18 (all YouTube channels)

---

## Active subscriptions (last_checked populated — confirmed working)

These have been successfully feeding the Check All workflow. The "Geopolitics prompt" referred to below is the standard one used across most subscriptions:

> *Provide a numbered list of the key points in this text. Provide two or three sentences per point to provide an adequate flavour, plus some pithy quotations. Clean up the quotations so as to exclude the ums and ahs, etc. Italicise the quotations. Do not skip over stuff.*

(Stored as `prompt_name: "Numbered list of key points"` for those that have it set — see Notes column.)

| # | Name | Channel ID | Min duration | Prompt | Notes |
|---|------|------------|---|---|---|
| 1 | Alexander Mercouris | UCwGpHa6rMLjSSCBlckm5khw | 25 min | Geopolitics | Cornerstone — daily uploads |
| 2 | Judge Napolitano (Judging Freedom) | UCDkEYb-TXJVWLvOokshtlsw | 25 min | Geopolitics | Frequently interviews Larry Johnson, Wilkerson, Marandi |
| 3 | Brian Berletic (The New Atlas) | UCVkSF37pPXkZbElFjBwUsEA | 25 min | Geopolitics | |
| 4 | Glenn Diesen | UCZFCDIHTe9HGxtIuVDpBz7g | 25 min | Geopolitics | Source for Pipedream automation prototype |
| 5 | Danny Haiphong | UCOxLhz6B_elvLflntSEfnzA | 25 min | Geopolitics | |
| 6 | Ben Norton (Geopolitical Economy Report) | UCwlvSJdcMc7iGdR-aducSog | 25 min | Geopolitics | |
| 7 | Rachel Blevins | UCR0qQlskMnffysEChGKqFpQ | 25 min | Geopolitics | |
| 8 | Chris Hedges (The Chris Hedges YouTube Channel) | UCEATT6H3U5lu20eKPuHVN8A | 25 min | Geopolitics | Stored name has stray newline — clean up on re-entry |
| 9 | Daniel Davis (Daniel Davis Deep Dive) | UCWDN5zr5ttctoIAhZwW6tcQ | 25 min | Geopolitics | High volume — multiple uploads/day |
| 10 | Owen Jones | UCSYCo8uRGF39qDCxF870K5Q | **20 min** | Geopolitics | Lower duration filter |
| 11 | Nima (Dialogue Works) | UCkF-6h_Zgf9zXNUmUB-MzTw | 25 min | Geopolitics | High volume |
| 12 | The Contrarian | UCTQY3JIbngitYLq1yukAAyQ | **10 min** | *(unset)* | Low duration filter; needs prompt assigned |
| 13 | Larry Johnson (Countercurrents) | UC_pqQXO1a71QWWjYTBFuRMg | 25 min | *(unset)* | Needs prompt assigned |

## Recently added — not yet checked

These were added but haven't been through Check Now yet (`last_checked: null`).

| # | Name | Channel ID | Min duration | Prompt | Notes |
|---|------|------------|---|---|---|
| 14 | Pascal Lottaz (Neutrality Studies) | *(missing — needs Resolve)* | 25 min | *(unset)* | URL also missing — incomplete entry |
| 15 | The Cradle | UC2liaNc5y50YBVjgXiQxdHQ | 25 min | *(unset)* | |
| 16 | Peak Prosperity | UCD2-QVBQi48RRQTD4Jhxu8w | 25 min | *(unset)* | |
| 17 | Unherd | UCMxiv15iK_MFayY_3fU9loQ | 25 min | *(unset)* | |
| 18 | The West Report | UCa3kU1spOTWHDmCxterTqIg | **10 min** | *(unset)* | Low duration filter |

---

## Default settings used across all subscriptions

- **Type:** YouTube Channel (all)
- **Look back hours:** 24
- **Enabled:** true
- **Schedule:** disabled (`schedule_enabled: false`) — feature not yet implemented
- **Default check interval / time:** 6 hours / 06:00 (placeholder values, unused)

## Items needing attention before / during re-entry

1. **Pascal Lottaz** — URL and channel_id both blank. Needs to be re-resolved from a fresh video link.
2. **Subscriptions 12–18** have empty `prompt_name`/`prompt_text` — they'd default to whatever the global prompt resolution does. On re-entry, decide explicitly whether each gets the standard Geopolitics prompt or something different.
3. **Chris Hedges name field** has a literal `\n` newline embedded (`"Chris Hedges (\nThe Chris Hedges YouTube Channel)"`) — strip on re-entry.
4. The list is plausibly worth grouping when the tree structure arrives. Suggested top-level categories based on content:
   - **Daily geopolitics commentators** (Mercouris, Napolitano, Diesen, Berletic, Davis, Nima, Haiphong, Norton, Blevins, Larry Johnson, The West Report)
   - **Long-form / less frequent** (Chris Hedges, Owen Jones, Pascal Lottaz, Unherd, The Contrarian)
   - **Outlets / aggregators** (The Cradle, Peak Prosperity)
   - This is a starter — reorganise to taste.

---

## Raw JSON (machine-readable copy)

The full raw JSON snapshot is preserved separately at `Roadmap/subscriptions_snapshot_2026-04-26.json` for a faithful restore.

---

*Snapshot taken: 26 April 2026*
