from __future__ import annotations

import argparse
import json
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analyzer import ActivityAnalyzer, analysis_metadata
from .config import DEFAULT_EVENTS_PATH, EVENT_LABELS, EVENT_TYPES, STATIC_DIR, WEIGHTS
from .engine import CultivationEngine
from .models import Event, ValidationError, utc_now_ts
from .store import JsonEventStore


class CultivationRequestHandler(BaseHTTPRequestHandler):
    engine: CultivationEngine
    store: JsonEventStore
    static_dir: Path
    analyzer: ActivityAnalyzer

    server_version = "CultivationLab/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/state":
            return self._handle_state()
        if parsed.path == "/events":
            return self._handle_events(parsed.query)
        if parsed.path == "/report/daily":
            return self._handle_daily_report(parsed.query)
        if parsed.path == "/metadata":
            return self._json(
                {
                    "event_types": EVENT_TYPES,
                    "event_labels": EVENT_LABELS,
                    "weights": WEIGHTS,
                }
            )
        if parsed.path in {"/", "/index.html"}:
            return self._static_file("index.html")
        return self._static_file(parsed.path.lstrip("/"))

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/state":
            events = self.store.load_events()
            return self._json(self.engine.snapshot(events).to_dict(), include_body=False)
        if parsed.path == "/report/daily":
            events = self.store.load_events()
            return self._json(self.engine.daily_report(events), include_body=False)
        if parsed.path == "/metadata":
            return self._json(
                {
                    "event_types": EVENT_TYPES,
                    "event_labels": EVENT_LABELS,
                    "weights": WEIGHTS,
                },
                include_body=False,
            )
        if parsed.path in {"/", "/index.html"}:
            return self._static_file("index.html", include_body=False)
        return self._static_file(parsed.path.lstrip("/"), include_body=False)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/event":
            return self._handle_post_event()
        if parsed.path == "/event/analyze":
            return self._handle_note_analysis(persist=False)
        if parsed.path == "/event/from-note":
            return self._handle_note_analysis(persist=True)
        self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        print(f"[api] {self.address_string()} - {format % args}")

    def _handle_state(self) -> None:
        events = self.store.load_events()
        self._json(self.engine.snapshot(events).to_dict())

    def _handle_events(self, query: str) -> None:
        params = parse_qs(query)
        limit = _parse_int(params.get("limit", ["100"])[0], default=100)
        events = self.store.load_events()
        deltas = self.engine.deltas_by_id(events)
        events.sort(key=lambda event: event.timestamp, reverse=True)
        payload = [event.to_dict() | {"delta": round(deltas.get(event.id, self.engine.event_delta(event)), 2)} for event in events[:limit]]
        self._json({"events": payload, "count": len(events)})

    def _handle_daily_report(self, query: str) -> None:
        params = parse_qs(query)
        raw_date = params.get("date", [None])[0]
        report_date = None
        if raw_date:
            try:
                report_date = date.fromisoformat(raw_date)
            except ValueError:
                return self._json({"error": "date must use YYYY-MM-DD format."}, status=HTTPStatus.BAD_REQUEST)
        events = self.store.load_events()
        self._json(self.engine.daily_report(events, day=report_date))

    def _handle_post_event(self) -> None:
        try:
            payload = self._read_json()
            if isinstance(payload, dict) and "events" in payload:
                raw_events = payload["events"]
                if not isinstance(raw_events, list):
                    raise ValidationError("events must be a list.")
                events = [Event.from_payload(item) for item in raw_events]
            else:
                events = [Event.from_payload(payload)]
        except ValidationError as exc:
            return self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except json.JSONDecodeError:
            return self._json({"error": "Request body must be valid JSON."}, status=HTTPStatus.BAD_REQUEST)

        self.store.append_events(events)
        all_events = self.store.load_events()
        deltas = self.engine.deltas_by_id(all_events)
        self._json(
            {
                "accepted": [
                    event.to_dict() | {"delta": round(deltas.get(event.id, self.engine.event_delta(event)), 2)}
                    for event in events
                ],
                "state": self.engine.snapshot(all_events).to_dict(),
            },
            status=HTTPStatus.CREATED,
        )

    def _handle_note_analysis(self, persist: bool) -> None:
        try:
            payload = self._read_json()
            event_type = payload.get("type")
            if event_type not in EVENT_TYPES:
                allowed = ", ".join(EVENT_TYPES)
                raise ValidationError(f"Unknown event type {event_type!r}. Allowed: {allowed}.")

            note = str(payload.get("note") or payload.get("text") or payload.get("transcript") or "").strip()
            if not note:
                raise ValidationError("note is required.")

            timestamp = int(payload.get("timestamp") or utc_now_ts())
            analysis = self.analyzer.analyze(event_type=event_type, note=note)
            event = Event.from_payload(
                {
                    "type": event_type,
                    "duration": analysis.duration_minutes * 60,
                    "timestamp": timestamp,
                    "metadata": analysis_metadata(analysis, note),
                }
            )
        except ValidationError as exc:
            return self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except json.JSONDecodeError:
            return self._json({"error": "Request body must be valid JSON."}, status=HTTPStatus.BAD_REQUEST)

        if not persist:
            deltas = self.engine.deltas_by_id([event])
            return self._json(
                {
                    "analysis": analysis.to_dict(),
                    "event": event.to_dict() | {"delta": round(deltas.get(event.id, self.engine.event_delta(event)), 2)},
                }
            )

        self.store.append_event(event)
        all_events = self.store.load_events()
        deltas = self.engine.deltas_by_id(all_events)
        self._json(
            {
                "analysis": analysis.to_dict(),
                "accepted": event.to_dict() | {"delta": round(deltas.get(event.id, self.engine.event_delta(event)), 2)},
                "state": self.engine.snapshot(all_events).to_dict(),
            },
            status=HTTPStatus.CREATED,
        )

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if not body:
            raise ValidationError("Request body is required.")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object.")
        return payload

    def _static_file(self, relative_path: str, include_body: bool = True) -> None:
        target = (self.static_dir / relative_path).resolve()
        static_root = self.static_dir.resolve()
        if static_root not in target.parents and target != static_root:
            return self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
        if not target.exists() or not target.is_file():
            return self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        content_type = guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if include_body:
            self.wfile.write(data)

    def _json(
        self,
        payload: dict,
        status: HTTPStatus = HTTPStatus.OK,
        include_body: bool = True,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if include_body:
            self.wfile.write(data)

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def build_server(
    host: str,
    port: int,
    events_path: Path = DEFAULT_EVENTS_PATH,
    static_dir: Path = STATIC_DIR,
) -> ThreadingHTTPServer:
    handler = type(
        "ConfiguredCultivationRequestHandler",
        (CultivationRequestHandler,),
        {
            "engine": CultivationEngine(),
            "store": JsonEventStore(events_path),
            "static_dir": static_dir,
            "analyzer": ActivityAnalyzer(),
        },
    )
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Cultivation Lab MVP server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--events-path", type=Path, default=DEFAULT_EVENTS_PATH)
    args = parser.parse_args()

    server = build_server(args.host, args.port, events_path=args.events_path)
    print(f"Cultivation Lab running at http://{args.host}:{args.port}")
    print(f"Event store: {args.events_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


def _parse_int(value: str, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 500))
