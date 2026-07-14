# Graph Explorer

The Graph Explorer is an interactive view for visually exploring the relationships
between sessions, STIX intelligence, and session metadata. It is served at
`/graph` and is available to every authenticated user.

## Concepts

The graph is built from **nodes** and **edges**. Nothing about the graph layout
or the "metadata" relationships is persisted — the graph is assembled on demand
from the existing database (sessions, STIX tables, STIX relationships).

### Node families

| Kind | Represents | Node id | Default shape |
|---|---|---|---|
| `session` | A tracked session (keyed by `fsid`) | `session:<fsid>` | circle with risk ring |
| `stix` | A STIX observable/SDO | `stix:<stix_id>` | diamond |
| `property` | A virtual metadata value (e.g. Platform: Win32) | `property:<field>:<value>` | rounded rectangle |
| `flag` | A triggered rule / risk flag | `flag:<flag>` | warning triangle (⚠) |

STIX nodes are labeled by their `name` when available (read from the `raw`
JSONB), so an autonomous system shows `AS204297 · <name>` rather than the bare
number.

### Edge families

| Kind | Between | Style | Source |
|---|---|---|---|
| `stix_relationship` | two STIX nodes | solid, arrow | persisted `stix_relationship` rows |
| `metadata` | session ↔ stix / property / flag | dashed | derived at query time |

Metadata edges are **visualization only** — they express that a session has a
given IP, user-agent, property value, or flag. They are never written to the DB.

## Node score ring

Session nodes render their `risk_score` two ways:

- The numeric score is drawn centered on the node.
- A red pie/ring fills proportionally to the score (0 = empty, 50 = half,
  100 = full). This can be toggled off and recolored in **Settings**.

## Seeding the graph

The graph opens from three places, all of which navigate to a single flexible
route carrying URL-encoded seeds:

```
/graph?seeds=<url-encoded JSON array>
```

Seed objects are either:

```json
{ "kind": "session", "fsid": "<fsid>" }
{ "kind": "stix", "type": "ipv4-addr", "value": "1.2.3.4" }
{ "kind": "stix", "stix_id": "autonomous-system--<uuid>" }
```

Launch points:

- **Dashboard** — tick the checkbox column on one or more rows, then **🕸 Explore
  in graph** (all selected sessions become seeds).
- **Session Detail** — **🕸 Explore in graph** (single session seed).
- **Intelligence** — **🕸 Explore in graph** on a loaded entity (single STIX seed).

When a session is seeded, its directly-linked IP and user-agent observables are
included so the graph is not empty on open.

## Expansion (one hop at a time)

Every expansion adds **exactly one hop** from the clicked node. To go deeper you
expand the newly-added nodes. Right-click a node to open the context panel, which
shows the node metadata plus the available expansions.

Each expansion option carries an **exact count of the new nodes it would add**
(after de-duplicating against nodes already on the graph). When that count meets
or exceeds the global warning threshold, the badge turns red and a confirmation
dialog is shown before the expansion runs. There is no hard cap — large
expansions are allowed after confirmation.

### Expansion options by node kind

| Node | Options (`key`) |
|---|---|
| `session` | `role:ip`, `role:user-agent`, `property:<field>`, `flag:<name>` |
| `stix` | `linked_sessions`, `reltype:<stix_type>` (one per related entity type) |
| `property` | `sessions` (all sessions sharing the value) |
| `flag` | `sessions` (all sessions carrying the flag) |

STIX relationship expansion is split **per related entity type** so you can
expand, say, only the Autonomous System or only the Country from an IP. Flags and
metadata options are presented in **searchable dropdowns** because a node may
have many of them.

### Property whitelist (v1)

Property nodes are limited to a curated whitelist so the graph stays readable:

| Field key | Label | Source column(s) |
|---|---|---|
| `platform` | Platform | `device_platform` |
| `timezone` | Timezone | `locale_internationalization_timezone` |
| `language` | Language | `locale_languages_language` |
| `screen_resolution` | Screen Resolution | `device_screen_resolution_width` × `_height` |

## Auto-linking

When a new node is added (by expansion, by the Add-entity drawer, or by a seed),
the client asks the backend for any edges between that node and nodes **already
present** and draws them. This ensures real relationships are shown even when the
neighbour already existed — e.g. expanding an AS from one IP immediately connects
it to every other IP of that AS already on the graph.

Auto-linking is controlled by the per-user setting `graph.autoLink` (default on)
and implemented server-side by `compute_links` (which only returns edges, never
new nodes).

## Bulk expansion

Select 2+ nodes of the **same type** (ctrl/⌘-click, or the *Select by type*
dropdown) and use **⛓ Bulk expand** in the bottom bar. The client fetches each
selected node's expansion options, unions them by category (summing counts), and
applies the chosen category to every selected entity. Example: select several
sessions and expand their IP address, a metadata field, or one specific flag.

## Interactions

| Action | Result |
|---|---|
| Wheel | zoom in/out |
| Drag on empty canvas | pan |
| Drag a node | move it |
| Ctrl/⌘ + click | add/remove node from selection |
| Drag a selected node | moves the whole selection |
| Right-click a node | open context panel (metadata + expansions + browse) |
| **Browse** (in panel) | open the Session or Intelligence view in a new tab |

Bottom bar: zoom in/out, fit, re-run layout, settings, delete selected, bulk
expand, *select by type*, and **＋ Add entity**.

### Add-entity drawer

The **＋ Add entity** button opens a right-side drawer to populate the graph:

1. **Search for** — pick Session or a STIX type.
2. **Filters (optional)** — the same condition builder used by the dashboard /
   intelligence views (field + operator + value; AND/OR for STIX).
3. **Results** — click **+** on a row to add it; the drawer stays open so you can
   add several.

## Settings

Graph settings are per-user and stored in `users.settings` (JSONB). Editable from
the in-graph **⚙ Settings** panel:

- Node colors — one per STIX type, plus session, metadata, and flag.
- Session risk ring — enable/disable and recolor.
- Behavior — automatically link new nodes to existing nodes (`graph.autoLink`).

The **expansion warning threshold** is a *global* setting (default `1000`),
editable by admins under **Administration → Graph Settings**.

## API

All endpoints require authentication (`Authorization: Bearer <jwt|api-token>`).

### Graph

```
POST /api/graph/seed        { "seeds": [ ... ] }            → { nodes, edges, threshold }
POST /api/graph/expansions  { "ref": {...}, "known_ids": [] } → { expansions, threshold }
POST /api/graph/expand      { "ref": {...}, "key": "..." }   → { nodes, edges }
POST /api/graph/links       { "ref": {...}, "known_ids": [] } → { edges }
```

A `ref` identifies a node: `{"kind":"session","fsid":...}`,
`{"kind":"stix","stix_id":...}`, `{"kind":"property","field":...,"value":...}`,
or `{"kind":"flag","value":...}`.

Each expansion option looks like:

```json
{ "key": "reltype:autonomous-system", "label": "Autonomous System",
  "category": "Autonomous System", "group": "relationships",
  "count": 3, "warn": false }
```

`group` is one of `linked | relationships | sessions | property | flag` and
drives how the UI renders the option (buttons vs. searchable dropdowns).

### Settings

```
GET  /api/settings/me        → merged user settings
PUT  /api/settings/me        merge a patch into users.settings
GET  /api/settings/global    → global settings (any user)
PUT  /api/settings/global    admin only; e.g. {"graph.expand_warn_threshold": 500}
```

## Backend layout

- `services/graph.py` — node/edge builders, `PROPERTY_FIELDS`, `STIX_TYPE_LABELS`,
  `resolve_seeds`, `get_expansions`, `expand`, `compute_links`.
- `routes/graph.py` — the four graph endpoints.
- `services/settings.py` — `USER_SETTINGS_DEFAULTS`, `GLOBAL_DEFAULTS`, merge helpers.
- `routes/settings.py` — user + global settings endpoints.
- `models/app_setting.py` — `app_settings` key/value table for global settings.
- `models/user.py` — `users.settings` JSONB column (added at startup by
  `services/database.py::_apply_column_upgrades` since there is no migration tool).

## Frontend layout

- `pages/Graph/Graph.jsx` — Cytoscape.js canvas, context menu, bulk panel,
  settings panel, add-entity drawer.
- `pages/Graph/graphLink.js` — `buildGraphUrl`, `parseSeeds`, `sessionSeed`,
  `stixSeed`.
- `hooks/useUserSettings.js` — loads/merges user settings from the backend.
- `components/GraphGlobalSettings` — admin threshold editor (in Administration).
