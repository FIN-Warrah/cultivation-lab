# Architecture

```text
Manual Input / Voice Text / Future Collectors
        |
        v
POST /event or POST /event/from-note
        |
        v
ActivityAnalyzer (OpenAI when configured, local fallback otherwise)
        |
        v
JsonEventStore (data/events.json)
        |
        v
CultivationEngine
        |
        +--> GET /state
        +--> GET /report/daily
        |
        v
Static Dashboard
```

## MVP Boundaries

Implemented now:

- Event ingestion API
- Natural-language activity analysis API
- Optional OpenAI Responses API provider with local fallback
- Milestone detection for insight and breakthrough events
- Browser text and voice note capture
- Weight-based cultivation score
- Time decay from event timestamps
- Realm mapping
- Heart demon risk heuristic
- Daily report
- Single-page dashboard

Deferred:

- VSCode extension
- Browser extension
- Git hooks
- Multi-user accounts
- Database migration layer

## Future Collector Shape

Collectors only need to emit the same event contract:

```json
{
  "type": "coding",
  "duration": 3600,
  "timestamp": 1710000000,
  "metadata": {
    "quality": 1.0,
    "source": "vscode"
  }
}
```

That keeps the ingestion API stable while new sources are added.

Natural-language entries are converted into the same contract. The analyzer stores its result under `metadata`:

```json
{
  "track": "master_phd",
  "track_label": "硕博连修",
  "quality": 1.34,
  "note": "跑了两个小时 baseline，定位了 loss 问题",
  "ai_feedback": "一线灵光贯穿泥丸宫...",
  "achievement_score": 80,
  "analysis_source": "local_ai or openai:<model>",
  "bonus_power": 1200,
  "realm_target": "渡劫期",
  "realm_floor_power": 3000
}
```

Milestone metadata is optional. When present, `bonus_power` is added to the ordinary weighted score, and `realm_floor_power` can lift the replayed state directly to a realm threshold.
The analyzer accepts four tracks: `master`, `phd`, `direct_phd`, and `master_phd`. Track selection changes the milestone table for proposal, midterm/qualifying, thesis submission, paper submission/acceptance, and defense events.
The current web dashboard stores the user's default track in browser local storage and sends it with note submissions; API callers may provide `track` per request.
