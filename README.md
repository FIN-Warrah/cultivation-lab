# Cultivation Lab

Cultivation Lab is a small MVP for quantifying academic behavior as a dynamic cultivation score. It accepts time-series research events, applies weighted scoring and decay, maps the score into cultivation realms, and serves a simple dashboard.

## Run

```bash
python3 app.py --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

Optional real AI analysis:

```bash
export OPENAI_API_KEY="sk-..."
export CULTIVATION_AI_MODEL="gpt-5.5"
python3 app.py --host 127.0.0.1 --port 8000
```

If no API key is configured, the app falls back to the built-in local analyzer. The key is only read by the backend and is never sent to the browser.

Supported AI environment variables:

- `OPENAI_API_KEY` or `CULTIVATION_AI_API_KEY`
- `CULTIVATION_AI_MODEL` or `OPENAI_MODEL`
- `CULTIVATION_AI_BASE_URL` or `OPENAI_BASE_URL`
- `CULTIVATION_AI_TIMEOUT`

Optional demo data:

```bash
python3 scripts/seed_demo.py
```

## API

Record a natural-language research note and let the app estimate duration, quality, cultivation gain, and feedback:

```bash
curl -X POST http://127.0.0.1:8000/event/from-note \
  -H 'Content-Type: application/json' \
  -d '{"type":"experiment_run","note":"跑了两个小时 diffusion baseline，定位了 loss 不收敛的问题并写了实验记录"}'
```

Preview the same AI-style analysis without saving:

```bash
curl -X POST http://127.0.0.1:8000/event/analyze \
  -H 'Content-Type: application/json' \
  -d '{"type":"paper_reading","note":"读完一篇 arxiv 论文并整理了三条可复现实验思路"}'
```

Record one behavior event:

```bash
curl -X POST http://127.0.0.1:8000/event \
  -H 'Content-Type: application/json' \
  -d '{"type":"coding","duration":3600,"timestamp":1710000000}'
```

`duration` is accepted in seconds and normalized to hours for scoring. A one-hour coding event adds `10` cultivation power before decay.

Record a batch:

```bash
curl -X POST http://127.0.0.1:8000/event \
  -H 'Content-Type: application/json' \
  -d '{"events":[{"type":"paper_reading","duration":5400},{"type":"writing","duration":3600}]}'
```

Read state:

```bash
curl http://127.0.0.1:8000/state
```

Read today's report:

```bash
curl http://127.0.0.1:8000/report/daily
```

## Event Types

- `coding`
- `paper_reading`
- `experiment_run`
- `writing`
- `meeting`
- `debugging`
- `browsing`
- `idle`

## Core Model

The MVP stores events in `data/events.json` and recomputes state deterministically from the append-only event log.

```text
score(event) = weight[type] * duration_hours * quality
P_t = decayed(previous_power) + score(event)
```

`quality` defaults to `1.0` and can be passed via `metadata.quality`, clamped to `0..2`.
Important nodes can also carry `metadata.bonus_power` and `metadata.realm_floor_power`.
The note analyzer uses this for breakthrough-style moments such as 有所感、顿悟、投稿、仙门赐符、雷劫将临 and 雷劫已渡.

The dashboard uses the note-based endpoint by default. The browser voice button uses the built-in Web Speech API when available, converts speech to text locally in the browser, then sends the text to `/event/from-note`.

The dashboard asks the user to choose an academic track on first use, stores it in browser local storage, and automatically attaches it to later note submissions. It can be changed from the main dashboard. API clients can still pass `track` explicitly:

- `master`: 硕士一程
- `phd`: 博士一程
- `direct_phd`: 直博玄门
- `master_phd`: 硕博连修

The track changes milestone strength. For example, a master defense pass enters `大乘期`, while doctoral/direct-PhD final defenses can enter `飞升期`; `master_phd` treats an explicit 硕士答辩 as a front tribulation and 博士/ final defense as the second tribulation.

Realm thresholds:

- `< 100`: 炼气期
- `100..299`: 筑基期
- `300..799`: 金丹期
- `800..1499`: 元婴期
- `1500..2999`: 化神期
- `3000..4999`: 渡劫期
- `5000..7999`: 大乘期
- `>= 8000`: 飞升期

## Tests

```bash
python3 -m unittest discover -s tests
```
