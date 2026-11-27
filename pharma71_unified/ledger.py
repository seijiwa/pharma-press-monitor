"""Transactional append-only audit and verified original ledger."""
import sqlite3,json
from pathlib import Path
def persist(db_path,audit):
    path=Path(db_path);path.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path,timeout=30)
    try:
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('PRAGMA synchronous=FULL')
        with con:
            con.execute('CREATE TABLE IF NOT EXISTS runs (run_key TEXT PRIMARY KEY, started TEXT NOT NULL, payload TEXT NOT NULL)')
            con.execute('CREATE TABLE IF NOT EXISTS originals (ticker TEXT NOT NULL, url TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(ticker,url))')
            key=str(audit.get('run_id') or audit['start_jst'])
            raw=json.dumps(audit,ensure_ascii=False,sort_keys=True)
            prior=con.execute('SELECT payload FROM runs WHERE run_key=?',(key,)).fetchone()
            if prior and prior[0]!=raw:raise ValueError('audit run key collision')
            con.execute('INSERT OR IGNORE INTO runs VALUES(?,?,?)',(key,audit['start_jst'],raw))
            for e in audit['entries']:
                for p in e['primary_releases']:
                    if p.get('original_confirmed') and p.get('url'):
                        con.execute('INSERT OR IGNORE INTO originals VALUES(?,?,?)',(e['ticker'],p['url'],json.dumps(p,ensure_ascii=False)))
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    finally:con.close()
