import psycopg2
from psycopg2.extras import DictCursor
from psycopg2.pool import SimpleConnectionPool
from app.config import Config

pool = None
try:
    pool = SimpleConnectionPool(
        1, 10,
        host=Config.DB_HOST,
        database=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        port=Config.DB_PORT
    )
except Exception:
    pass

class DBContext:
    def __init__(self, conn):
        self.conn = conn
        self._cur = None

    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)

    def execute(self, query, params=None):
        self._cur = self.conn.cursor(cursor_factory=DictCursor)
        self._cur.execute(query, params)
        return self._cur

    def fetchone(self):
        return self._cur.fetchone() if self._cur else None

    def fetchall(self):
        return self._cur.fetchall() if self._cur else []

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

def get_db():
    if not pool:
        yield None
        return
    conn = pool.getconn()
    try:
        yield DBContext(conn)
    except Exception:
        conn.rollback()
        raise
    finally:
        # Always rollback any uncommitted transaction before returning to pool
        try:
            conn.rollback()
        except Exception:
            pass
        pool.putconn(conn)
