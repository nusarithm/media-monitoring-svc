import asyncio, os, pathlib
from dotenv import load_dotenv
load_dotenv(".env")
import asyncpg

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    await conn.execute(pathlib.Path("migrations/schema.sql").read_text())
    cols = await conn.fetch("""select column_name, data_type from information_schema.columns
                               where table_name='sosmed_keyword' order by ordinal_position""")
    print("kolom:", [(c["column_name"], c["data_type"]) for c in cols])
    rows = await conn.fetch("select id, keyword, platform, enabled, last_scraped_at from sosmed_keyword")
    print("isi   :", [dict(r) for r in rows])
    await conn.close()

asyncio.run(main())
