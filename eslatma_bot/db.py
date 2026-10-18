"""Postgres (Neon) уловчиси: sqlite3 уловчисига ўхшаб ишлайди, шунда logic.py/bot.py бир хил қолади.
Ўзгаришлар: ? -> %s, lastrowid (RETURNING), сервер ухлаб уйғонса қайта уланиш, транзакция хатосидан кейин rollback."""
import re, threading
import psycopg


class Row:
    """sqlite3.Row каби: r["ном"], r[0], dict(r), for v in r."""
    __slots__ = ("_k", "_v")

    def __init__(self, keys, values):
        self._k, self._v = keys, values

    def __getitem__(self, i):
        if isinstance(i, slice):
            return tuple(self._v[i])
        return self._v[i] if isinstance(i, int) else self._v[self._k.index(i)]

    def keys(self):
        return list(self._k)

    def __iter__(self):
        return iter(self._v)

    def __len__(self):
        return len(self._v)


def _row_factory(cursor):
    keys = [c.name for c in (cursor.description or [])]
    return lambda values: Row(keys, values)


class Cur:
    """Курсор ўрами: lastrowid қўшилади, қолгани psycopg курсорига узатилади."""
    def __init__(self, cur, lastrowid):
        self._c, self.lastrowid = cur, lastrowid
        self.rowcount = cur.rowcount

    def fetchone(self):
        return self._c.fetchone()

    def fetchall(self):
        return self._c.fetchall()

    def __iter__(self):
        return iter(self._c)


RETURNING_TABLES = re.compile(r"^\s*INSERT\s+INTO\s+(reminders|feedback)\b", re.I)


def to_pg_ddl(sql):
    """SQLite схемасини Postgres'га: telegram ID'лар int32 га сиғмайди (BIGINT), вақт (DOUBLE) аниқлиги."""
    sql = re.sub(r"INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", sql)
    sql = re.sub(r"\bINTEGER\b", "BIGINT", sql)
    return re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql)


class PgConn:
    def __init__(self, url):
        self.url = url
        self.lock = threading.RLock()
        self.conn = None
        self._connect()

    def _connect(self):
        # prepare_threshold=None: Neon пулери (pgbouncer) тайёрланган сўровларни кўтармайди
        self.conn = psycopg.connect(self.url, row_factory=_row_factory, prepare_threshold=None, connect_timeout=15)

    def execute(self, sql, params=()):
        with self.lock:
            q = sql.replace("?", "%s")
            ret = bool(RETURNING_TABLES.match(q))
            if ret:
                q += " RETURNING id"
            for attempt in (1, 2):
                try:
                    cur = self.conn.execute(q, params)
                    break
                except (psycopg.OperationalError, psycopg.InterfaceError):
                    if attempt == 2:
                        raise
                    self._connect()  # сервер ухлаб қолган ёки уланиш узилган
                except Exception:
                    self.conn.rollback()  # ярим қолган транзакция кейинги сўровларни бузмасин
                    raise
            return Cur(cur, cur.fetchone()[0] if ret else None)

    def executescript(self, script):
        for stmt in [s.strip() for s in script.split(";") if s.strip()]:
            self.execute(stmt)
        self.commit()

    def commit(self):
        with self.lock:
            try:
                self.conn.commit()
            except (psycopg.OperationalError, psycopg.InterfaceError):
                self._connect()

    def rollback(self):
        with self.lock:
            self.conn.rollback()

    def close(self):
        self.conn.close()
