import json
import os
import psycopg2
from psycopg2 import sql
import dotenv

dotenv.load_dotenv()
old_conn = psycopg2.connect(
    dbname='postgres',
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'),
    host=os.getenv('POSTGRES_HOST'),
    port=os.getenv('POSTGRES_PORT')
)

old_conn.autocommit = True
old_c = old_conn.cursor()

dbname = 'cryptodb'
try:
    old_c.execute(sql.SQL("CREATE DATABASE {}").format(
        sql.Identifier(dbname)
    ))

except Exception as e:
    print(f"An error occurred: {e}")

old_c.close()
old_conn.close()

conn = psycopg2.connect(
    dbname='cryptodb',
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'),
    host=os.getenv('POSTGRES_HOST'),
    port=os.getenv('POSTGRES_PORT')
)

conn.autocommit = True
c = conn.cursor()


def setup_db():
    conn = psycopg2.connect(
        dbname='cryptodb',
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        host=os.getenv('POSTGRES_HOST'),
        port=os.getenv('POSTGRES_PORT')
    )
    conn.autocommit = True  # Enable autocommit mode
    c = conn.cursor()

    try:
        c.execute('''
            CREATE TABLE IF NOT EXISTS wallets (
                id BIGSERIAL PRIMARY KEY,
                address VARCHAR(255),
                private_key VARCHAR(255)
            )
        ''')

    except Exception as e:
        print(f"An error occurred while setting up the database: {e}")
    finally:
        c.close()
        conn.close()


def add_address(address: str, private_key: str):
    c.execute(f'''
    INSERT INTO "wallets" (address, private_key)
    VALUES (%s, %s)
    ''', (address, private_key))


def get_all_addresses():
    c.execute(f'SELECT address FROM wallets')
    result = c.fetchall()
    if result:
        return [res[0] for res in result]
    return []


def get_private_key(address):
    c.execute(f'SELECT private_key FROM wallets WHERE address = %s', (address, ))
    result = c.fetchone()
    if result:
        return result[0]
    return []