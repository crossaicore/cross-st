# Container Format — subject.json

Every Cross workflow revolves around a single JSON file — conventionally named `subject.json` after your topic (e.g. `stain-on-baltic-birch.json`). This file is created by `st-gen` or `st-bang`, extended by `st-cross` and `st-fact`, and read by nearly every other `st-*` command.

Understanding the container lets you inspect, pipe, and post exactly the content you want.

---

## Structure at a glance

```
subject.json
├── data[]            ← one entry per AI generation run
│   ├── make          configured agent name (legacy: provider)
│   ├── model         "gpt-4o"
│   ├── prompt        user-authored generation/update instructions
│   ├── data_id       opaque association ID
│   ├── gen_payload   actual API request body (including assembled instructions)
│   ├── gen_response  raw API response
│   ├── timing        wall-clock and token metrics
│   └── md5_hash      fingerprint of prompt + model (dedup key)
│
└── story[]           ← one entry per prepared report
    ├── make          configured agent name (legacy: provider)
    ├── source_data_id associated raw generation ID
    ├── model         "gpt-4o"
    ├── title         short headline (≤ 10 words)
    ├── markdown      full report body in Markdown
    ├── text          plain-text version (no Markdown syntax)
    ├── spoken        TTS-friendly variant (no symbols, no tables)
    ├── hashtags      list of hashtag strings
    ├── md5_hash      fingerprint of the story content
    ├── topic_id      Discourse topic ID (set after st-post)
    ├── post_url      full Discourse URL (set after st-post)
    ├── mp3_url       Discourse audio URL (set after st-post --mp3)
    └── fact[]        ← one entry per fact-check run
        ├── make      AI provider that ran the fact-check
        ├── model     model used
        ├── score     numeric accuracy score (0–2 scale)
        ├── counts    [true, partially_true, opinion, partially_false, false]
        ├── report    full fact-check report in Markdown
        ├── summary   markdown table summarising claim verdicts
        └── md5_hash  fingerprint of the fact-check
```

---

## After a full `st-cross` run (5 providers)

```
subject.json
├── data[5]           one raw generation per AI
└── story[5]          one prepared report per AI
    └── fact[5]       each story checked by all 5 AIs = 25 fact entries total
```

The resulting 5 × 5 truth matrix — every AI checking every other AI's report — is what makes Cross unique.

---

## `data[]` — raw generation entries

Created by generation and update commands. Multiple entries can belong to the same agent or provider/model.

| Key | Type | Description |
|-----|------|-------------|
| `make` | string | Configured agent name in current generators; legacy entries can contain a provider name |
| `data_id` | string | Opaque ID linking this raw entry to prepared reports |
| `model` | string | Exact model string used, e.g. `"gpt-4o"`, `"claude-sonnet-4-5"` |
| `prompt` | string | User-authored generation instructions or update request; the assembled API request is retained in `gen_payload` |
| `gen_payload` | object | Complete API request body (`model`, `max_tokens`, `system`, `messages`) |
| `gen_response` | object | Raw API response object as returned by the provider |
| `timing` | object | Performance metrics (see below) |
| `md5_hash` | string | MD5 of prompt + model string — used by `st-cross` to detect duplicate runs |

### `timing` object

| Key | Type | Description |
|-----|------|-------------|
| `start_time` | float | Unix timestamp when the API call was made |
| `end_time` | float | Unix timestamp when the response was received |
| `elapsed_seconds` | float | Wall-clock duration, e.g. `35.612` |
| `tokens_input` | int | Prompt tokens consumed |
| `tokens_output` | int | Completion tokens generated |
| `tokens_total` | int | Total tokens billed |
| `tokens_per_second` | float | Output throughput |
| `cached` | bool | `true` if this response was served from the local API cache |

---

## `story[]` — prepared report entries

Created by `st-prep` (called automatically by `st-gen`) and commands that prepare new outputs. Each entry contains the human-readable versions of one report. Several reports can have the same provider/model.

| Key | Type | Description |
|-----|------|-------------|
| `make` | string | Authoring agent name; legacy entries can contain a provider name |
| `source_data_id` | string | ID of the associated raw generation entry |
| `model` | string | Exact model string |
| `title` | string | Short headline, ≤ 10 words — used as the Discourse topic title |
| `markdown` | string | Full report body in Markdown — posted by `st-post`, edited by `st-edit` |
| `text` | string | Plain-text version with Markdown syntax stripped |
| `spoken` | string | TTS-friendly variant — no symbols, tables, or code blocks; used by `st-speak` |
| `hashtags` | array | List of hashtag strings, e.g. `["#DIYFurniture", "#Woodworking"]` |
| `md5_hash` | string | Fingerprint of the story content |
| `topic_id` | int / null | Discourse topic ID — written by `st-post` after a successful post |
| `post_url` | string | Full Discourse URL — written by `st-post` |
| `mp3_url` | string | Discourse CDN URL for the uploaded audio — written by `st-post` when an MP3 is attached |
| `fact` | array | Fact-check results (see below) — populated by `st-fact` / `st-cross` |

### `story[].fact[]` — fact-check entries

Created by `st-fact`. Each story can have multiple fact-check entries — one per AI provider that checked it. After a full `st-cross` run, every story has 5 fact entries (one per checker).

| Key | Type | Description |
|-----|------|-------------|
| `make` | string | AI provider that ran the fact-check |
| `model` | string | Exact model string |
| `score` | float | Accuracy score on a 0–2 scale (2 = all claims verified true) |
| `counts` | array | `[true, partially_true, opinion, partially_false, false]` — count of claims in each verdict category |
| `report` | string | Full fact-check report in Markdown — posted as a reply by `st-post -f N` |
| `summary` | string | Compact Markdown table of claim verdicts — shown by `st-analyze` and `st-verdict` |
| `md5_hash` | string | Fingerprint of the fact-check content |

---

## Minimal example

A container immediately after `st-gen` (one AI, no fact-checks yet):

```json
{
  "data": [
    {
      "make": "openai",
      "model": "gpt-4o",
      "prompt": "Write a 1200-word report on the best wood stains for Baltic Birch...",
      "gen_payload": { "model": "gpt-4o", "max_tokens": 4096, "messages": ["..."] },
      "gen_response": { "...": "..." },
      "timing": {
        "start_time": 1774212924.4,
        "end_time": 1774212960.0,
        "elapsed_seconds": 35.6,
        "tokens_input": 260,
        "tokens_output": 3696,
        "tokens_total": 7650,
        "tokens_per_second": 214.8,
        "cached": false
      },
      "md5_hash": "cbc2f270386e5ede7413734adaa5c3c9"
    }
  ],
  "story": [
    {
      "make": "openai",
      "model": "gpt-4o",
      "title": "Best Wood Stains for Baltic Birch Furniture",
      "markdown": "# Best Wood Stains for Baltic Birch Furniture\n\n...",
      "text": "Best Wood Stains for Baltic Birch Furniture\n\n...",
      "spoken": "Best Wood Stains for Baltic Birch Furniture. ...",
      "hashtags": ["#Woodworking", "#DIYFurniture", "#HomeImprovement"],
      "fact": [],
      "md5_hash": "d57eb81b4d0b920ce7dc189f972a52aa",
      "topic_id": null,
      "post_url": "",
      "mp3_url": ""
    }
  ]
}
```

---

## Lifecycle — how the container grows

| Step | Command | What is added |
|------|---------|---------------|
| 1 | `st-gen subject.prompt` | `data[0]` + `story[0]` (one AI) |
| 1b | `st-bang subject.prompt` | `data[0..4]` + `story[0..4]` (all 5 AIs in parallel) |
| 2 | `st-cross subject.json` | `story[n].fact[]` — 25 entries for a 5-provider run |
| 3 | `st-post subject.json` | `story[n].topic_id`, `.post_url`, `.mp3_url` |
| 4 | `st-fix subject.json` | Appends a generated fix and its prepared report |
| 4b | `st-merge subject.json` | Appends a new `story[]` entry (merged from multiple AI reports) |
| 5 | `st-update -s 1 subject.json` | Appends an associated raw entry and updated report |
| 5b | `st-update -s 1 --iterate 2 subject.json` | Replaces existing update output 2 and its associated raw entry together |
| 6 | `st-rm -s 2 subject.json` | Removes report 2 and its associated raw entry; later indices shift down |

## Report associations and updates

New raw entries have an opaque `data_id`; prepared reports refer to it through `source_data_id`. This links a report to the generation that produced it. Do not infer associations from matching array positions or matching provider/model names. Older ambiguous associations are rejected by operations that require an exact pair.

`st-update` adds these ordinary metadata fields:

| Location | Field | Meaning |
|---|---|---|
| Raw entry | `prompt`, `update_request` | User-authored update instructions |
| Raw entry and report | `base_prompt` | Original authored intent carried into the update |
| Raw entry | `markdown` | Generated report body extracted from the structured AI response |
| Raw entry | `update_summary` | Actual Markdown diff and line counts, AI explanations, uncertainties, and output SHA-256 |
| Prepared report | `authored_prompt` | Update instructions used for this output and its scoring |
| Container | `_st_update` | Records that an update has existed, including after outputs are removed |

The raw `gen_payload` and `gen_response` still record the actual API exchange. Update requests and the original intent are stored separately from the assembled API prompt. AI reasons and source attributions in `update_summary` are unverified explanations; the local Markdown diff records what actually changed.

An append preserves all existing entries. Iteration prepares the full replacement pair before an atomic save; it discards the previous target only on success. Updated content does not inherit fact-checks or publication state. There is no active-report pointer, version graph, or ancestry footer. CLI indices remain current one-based array positions. Charts and rankings distinguish separate reports, including original and updated outputs from the same provider/model, using labels such as `provider:model [S6]` where needed.

See [st-update](st-update) for selection, review, and iteration examples.

---

## Reading the container from the CLI

```bash
st-cat subject.json                  # print the prompt (default)
st-cat --prompt -s 2 subject.json    # print report 2's authored prompt/request
st-cat -t subject.json               # print the title of story 1
st-cat --markdown subject.json       # print the Markdown body
st-cat --text subject.json           # print the plain-text body
st-cat --hashtags subject.json       # print hashtags
st-cat -f 1 subject.json             # print fact-check report 1
st-cat --markdown -s 3 subject.json  # print story 3's Markdown
```

**Related:** [st-gen](st-gen) · [st-bang](st-bang) · [st-prep](st-prep) · [st-cross](st-cross) · [st-fact](st-fact) · [st-cat](st-cat) · [st-post](st-post) · [st-analyze](st-analyze)


### Publication receipts

Optional top-level `_publications[]` retains known remote titles, site URLs, topic IDs, and post URLs independently of the local report. It supports duplicate-title checks after a local report is edited, replaced, or removed. It does not contain report versions and does not synchronize remote content. Report-level post fields describe the currently attached publication only. If a remote post succeeds but the container cannot be saved, a `.cross-receipts/*.receipt` recovery file preserves the returned publication details.
