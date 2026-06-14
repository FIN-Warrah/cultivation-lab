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
  "quality": 1.34,
  "note": "跑了两个小时 baseline，定位了 loss 问题",
  "ai_feedback": "实验突破这一段很顶...",
  "achievement_score": 80,
  "analysis_source": "local_ai or openai:<model>"
}
```
