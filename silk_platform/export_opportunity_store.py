"""Tenant-scoped persistence for export opportunities; no network operations."""
import json
import time
from .db import now_iso

LINK_VALID = 'COALESCE((s.id IS NOT NULL AND s.product_id=o.product_id AND s.hs_code=o.hs_code AND s.market_pref=o.market_iso3),0)'
JOIN = ' FROM export_opportunities o LEFT JOIN studies s ON s.id=o.study_id AND s.owner_id=o.account_id '


def owned(conn, account, oid):
    row = conn.execute('SELECT * FROM export_opportunities WHERE account_id=? AND id=?', (account, oid)).fetchone()
    return dict(row) if row else None


def find(conn, account, product, exporter, market, hs):
    row = conn.execute('SELECT * FROM export_opportunities WHERE account_id=? AND product_id=? AND exporter=? AND market=? AND hs_code=?', (account, product, exporter, market, hs)).fetchone()
    return dict(row) if row else None


def event(conn, account, kind):
    conn.execute('INSERT INTO export_opportunity_events(account_id,kind,created_at) VALUES(?,?,?)', (account, kind, now_iso()))


def admit(conn, account, limit=30):
    """Atomic account-wide minute limit, shared by processes. No slow work in lock."""
    window = int(time.time()) // 60
    conn.execute('BEGIN IMMEDIATE')
    conn.execute('''INSERT INTO export_opportunity_rate_windows(account_id,window_start,hits) VALUES(?,?,1)
        ON CONFLICT(account_id) DO UPDATE SET window_start=excluded.window_start,
        hits=CASE WHEN window_start=excluded.window_start THEN hits+1 ELSE 1 END''', (account, window))
    hits = conn.execute('SELECT hits FROM export_opportunity_rate_windows WHERE account_id=?', (account,)).fetchone()[0]
    if hits > limit:
        conn.rollback()
        return False
    # The dashboard offers at most 90 days. Keep request telemetry bounded;
    # saved snapshots, study links and last source timestamps are never pruned.
    conn.execute("DELETE FROM export_opportunity_events WHERE id IN (SELECT id FROM export_opportunity_events WHERE created_at < strftime('%Y-%m-%dT%H:%M:%SZ','now','-91 days') LIMIT 500)")
    conn.commit()
    return True


def record_source(conn, account, provenance=None, failed=False):
    stamp = now_iso()
    event(conn, account, 'source_error' if failed else 'source_success')
    conn.execute('INSERT OR IGNORE INTO export_opportunity_source_status(id) VALUES(1)')
    if failed:
        conn.execute('UPDATE export_opportunity_source_status SET last_failure_at=? WHERE id=1', (stamp,))
    else:
        conn.execute('UPDATE export_opportunity_source_status SET last_success_at=?,last_retrieved_at=?,cached=? WHERE id=1',
                     (stamp, provenance['retrieved_at'], int(bool(provenance.get('cached')))))
    conn.commit()


def listing(conn, account, *, page, page_size, archived):
    where = ' WHERE o.account_id=? AND ' + ('o.archived_at IS NOT NULL' if archived else 'o.archived_at IS NULL')
    summary = conn.execute('SELECT COUNT(*) total, COALESCE(SUM('+LINK_VALID+'),0) linked, COALESCE(SUM('+LINK_VALID+" AND s.state='completed'),0) completed"+JOIN+where, (account,)).fetchone()
    total = summary['total']
    page = min(page, max(1, (total + page_size - 1) // page_size))
    rows = conn.execute('SELECT o.*, s.state study_state, s.id linked_study_id, '+LINK_VALID+' scope_matches'+JOIN+where+' ORDER BY o.id DESC LIMIT ? OFFSET ?', (account, page_size, (page-1)*page_size)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item['snapshot'] = json.loads(item['snapshot'])
        item['link_status'] = ('none' if not item['study_id'] else 'deleted' if not item['linked_study_id'] else 'valid' if item['scope_matches'] else 'changed')
        result.append(item)
    return {'opportunities':result, 'page':page, 'page_size':page_size, 'total':total, 'summary':dict(summary)}


def save(conn, account, product, exporter, market, iso3, snapshot):
    old = find(conn, account, product['id'], exporter, market, product['hs_code'])
    if old:
        # Saving an archived opportunity means the factory wants it back in its
        # active shortlist. Treat the existing row as the canonical snapshot and
        # restore it instead of silently leaving it hidden from the dashboard.
        if old.get('archived_at'):
            conn.execute('UPDATE export_opportunities SET archived_at=NULL WHERE account_id=? AND id=?', (account, old['id']))
            event(conn, account, 'saved')
        return old['id'], False
    row = snapshot['row']
    cur = conn.execute('''INSERT INTO export_opportunities
        (account_id,product_id,exporter,market,market_iso3,hs_code,market_name,snapshot,created_at)
        VALUES(?,?,?,?,?,?,?,?,?)''', (account,product['id'],exporter,market,iso3,product['hs_code'],row['item']['name'],json.dumps(snapshot,ensure_ascii=False,allow_nan=False),now_iso()))
    event(conn, account, 'saved')
    return cur.lastrowid, True


def set_archive(conn, account, oid, archived):
    conn.execute('UPDATE export_opportunities SET archived_at=? WHERE account_id=? AND id=?', (now_iso() if archived else None, account, oid))


def link_study(conn, account, oid, sid, notes):
    conn.execute('UPDATE export_opportunities SET study_id=?,study_requested_at=?,notes=? WHERE account_id=? AND id=?', (sid,now_iso(),notes,account,oid))
    event(conn, account, 'study_requested')


def metrics(conn, days):
    cutoff = conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ','now',?)", (f'-{days} days',)).fetchone()[0]
    counts = {r['kind']:r['n'] for r in conn.execute('SELECT kind,COUNT(*) n FROM export_opportunity_events WHERE created_at>=? GROUP BY kind',(cutoff,))}
    active = conn.execute('SELECT COUNT(DISTINCT account_id) FROM export_opportunity_events WHERE created_at>=?',(cutoff,)).fetchone()[0]
    states = {r['state']:r['n'] for r in conn.execute('SELECT s.state,COUNT(*) n'+JOIN+' WHERE o.study_requested_at>=? AND '+LINK_VALID+' GROUP BY s.state',(cutoff,))}
    changed = conn.execute('SELECT COUNT(*)'+JOIN+' WHERE o.study_requested_at>=? AND s.id IS NOT NULL AND NOT '+LINK_VALID,(cutoff,)).fetchone()[0]
    top = [dict(r) for r in conn.execute('SELECT market,market_name,COUNT(*) n FROM export_opportunities WHERE created_at>=? GROUP BY market,market_name ORDER BY n DESC,market LIMIT 8',(cutoff,))]
    source = conn.execute('SELECT last_success_at,last_failure_at,last_retrieved_at,cached FROM export_opportunity_source_status WHERE id=1').fetchone()
    return {'days':days,'active_factories':active,'events':counts,'study_states':states,'changed_study_links':changed,'top_markets':top,'source':dict(source) if source else {},'scope':'aggregate_only','generated_at':now_iso()}
