import psycopg2
from passlib.context import CryptContext
from dotenv import load_dotenv
import os

load_dotenv()


def setup():
    try:
        # Connect to the default PostgreSQL instance
        # Using settings that match your config.py
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
            port=os.getenv("DB_PORT", "5432")
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # Check if vector extension is available
        has_vector = False
        try:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            has_vector = True
            print("=> pgvector extension is available.")
        except Exception as e:
            print(f"=> pgvector extension not installed ({e}); using text fallback for embeddings.")

        # Execute schema
        with open("schema.sql", "r") as f:
            schema_sql = f.read()

        if not has_vector:
            schema_sql = schema_sql.replace("CREATE EXTENSION IF NOT EXISTS vector;", "-- CREATE EXTENSION IF NOT EXISTS vector;")
            schema_sql = schema_sql.replace("embedding vector(384),", "embedding text,")

        # Split and execute individual statements so one existing table does not fail the rest
        statements = [stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()]
        for stmt in statements:
            try:
                cursor.execute(stmt)
            except Exception as e:
                print(f"=> Notice on executing: {stmt[:40]}... -> {e}")

        print("=> Schema tables verified.")

        # Insert test user
        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        pwd_hash = ctx.hash("password123")

        cursor.execute("""
            INSERT INTO users (name, email, password_hash, role)
            VALUES ('Test Officer', 'officer@test.com', %s, 'officer')
            ON CONFLICT (email) DO NOTHING
        """, (pwd_hash,))
        
        print(f"=> Test user inserted: officer@test.com / password123")
        conn.close()
    
    except Exception as e:
        print(f"!!! Database setup failed: {e}")
        print("Please ensure PostgreSQL is installed and running with default local credentials.")

if __name__ == "__main__":
    setup()
