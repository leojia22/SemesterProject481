#!/usr/bin/env python3
"""ES Futures Trade Simulator - HTTP Server"""

import csv
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
PORT = 8081

def load_data(csv_path):
    print(f"Loading {csv_path} ...", flush=True)
    snapshots = []       # list of snapshot dicts, indexed by integer
    ts_index = {}        # timestamp -> snapshot index

    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = row['timestamp']
            if ts not in ts_index:
                ts_index[ts] = len(snapshots)
                snapshots.append({
                    'timestamp': ts,
                    'es_price': 0.0,
                    'spx_price': 0.0,
                    'asks': [],
                    'bids': [],
                })

            idx = ts_index[ts]
            snap = snapshots[idx]

            # Populate top-level prices from first row of this snapshot
            if snap['es_price'] == 0.0:
                try:
                    snap['es_price'] = round(float(row['current_es_price']) / 100, 2)
                    snap['spx_price'] = round(float(row['spx_price']), 2)
                except (ValueError, KeyError):
                    pass

            try:
                strike = float(row['future_strike'])
            except (ValueError, KeyError):
                continue

            # Parse MBO quantity (MBO_1 is the top-of-book size)
            qty = 0.0
            mbo_raw = row.get('MBO', '').strip().strip('[]')
            if mbo_raw:
                for val in mbo_raw.split(','):
                    try:
                        qty += float(val.strip())
                    except ValueError:
                        pass

            def safe_float(key, default=0.0):
                v = row.get(key, '').strip()
                try:
                    return round(float(v), 6) if v else default
                except ValueError:
                    return default

            entry = {
                's': strike,          # strike / price level
                'q': round(qty, 1),   # quantity
                'ps': safe_float('MBO_pulling_stacking'),
                'spx': safe_float('spx_strike'),
                't': safe_float('t'),
                'cd': safe_float('call_delta'),
                'cg': safe_float('call_gamma'),
                'ct': safe_float('call_theta'),
                'cv': safe_float('call_vega'),
                'cch': safe_float('call_charm'),
                'cr': safe_float('call_rho'),
                'cva': safe_float('call_vanna'),
                'cvo': safe_float('call_vomma'),
                'pd': safe_float('put_delta'),
                'pg': safe_float('put_gamma'),
                'pt': safe_float('put_theta'),
                'pv': safe_float('put_vega'),
                'pch': safe_float('put_charm'),
                'pr': safe_float('put_rho'),
                'pva': safe_float('put_vanna'),
                'pvo': safe_float('put_vomma'),
            }

            side = row.get('Side', '')
            if side == 'Ask':
                snap['asks'].append(entry)
            elif side == 'Bid':
                snap['bids'].append(entry)

    # Sort each snapshot's book
    for snap in snapshots:
        snap['asks'].sort(key=lambda x: x['s'])   # ascending (lowest ask first)
        snap['bids'].sort(key=lambda x: x['s'], reverse=True)  # descending (highest bid first)

    print(f"Loaded {len(snapshots)} snapshots.", flush=True)
    return snapshots


class Handler(BaseHTTPRequestHandler):
    all_levels = {}   # level_name -> snapshots list
    level_names = []  # ordered list of level names

    def _get_snapshots(self, qs):
        level = qs.get('level', [self.level_names[0]])[0] if self.level_names else None
        return self.all_levels.get(level, self.all_levels.get(self.level_names[0], []))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == '/' or path == '/index.html':
            self._serve_static('index.html', 'text/html; charset=utf-8')
        elif path == '/api/levels':
            self._json({'levels': self.level_names})
        elif path == '/api/meta':
            snapshots = self._get_snapshots(qs)
            self._json({
                'total': len(snapshots),
                'first_ts': snapshots[0]['timestamp'] if snapshots else '',
                'last_ts': snapshots[-1]['timestamp'] if snapshots else '',
            })
        elif path == '/api/snapshot':
            snapshots = self._get_snapshots(qs)
            try:
                idx = int(qs.get('idx', ['0'])[0])
            except (ValueError, IndexError):
                idx = 0
            idx = max(0, min(idx, len(snapshots) - 1))
            snap = snapshots[idx]

            # Compute live mid price from order book
            best_bid = snap['bids'][0]['s'] if snap['bids'] else snap['es_price']
            best_ask = snap['asks'][0]['s'] if snap['asks'] else snap['es_price']
            mid_price = round((best_bid + best_ask) / 2, 4)

            self._json({
                'idx': idx,
                'timestamp': snap['timestamp'],
                'es_price': snap['es_price'],
                'mid_price': mid_price,
                'best_bid': best_bid,
                'best_ask': best_ask,
                'spx_price': snap['spx_price'],
                'asks': snap['asks'][:40],
                'bids': snap['bids'][:40],
            })
        elif path == '/api/prices':
            snapshots = self._get_snapshots(qs)
            # Return mid price (from order book) for all snapshots (for chart)
            def mid(s):
                bb = s['bids'][0]['s'] if s['bids'] else s['es_price']
                ba = s['asks'][0]['s'] if s['asks'] else s['es_price']
                return round((bb + ba) / 2, 4)

            self._json({
                'prices': [mid(s) for s in snapshots],
                'timestamps': [s['timestamp'] for s in snapshots],
            })
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_static(self, filename, content_type):
        filepath = os.path.join(os.path.dirname(__file__), filename)
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def _json(self, data):
        content = json.dumps(data, separators=(',', ':')).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, fmt, *args):
        pass  # suppress access logs


def main():
    csv_files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith('.csv'))
    for fname in csv_files:
        name = fname[:-4]  # strip .csv
        Handler.all_levels[name] = load_data(os.path.join(DATA_DIR, fname))
        Handler.level_names.append(name)

    port = int(os.environ.get("PORT", 8081))
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"\n  Trade Simulator running", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == '__main__':
    main()
