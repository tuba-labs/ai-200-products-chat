"""Runs INSIDE the VNet via a short-lived pod; never print huge vectors."""
from rag_core.config import load_settings

settings = load_settings()
with settings.connect() as connection:
    for row in connection.execute('''SELECT p.name,p.manual_id,p.status,count(c.chunk_index),
                min(vector_dims(c.embedding)),max(vector_dims(c.embedding))
            FROM products p LEFT JOIN manual_chunks c ON c.manual_id=p.manual_id
            GROUP BY p.id ORDER BY p.created_at'''):
        print('product=%s manual=%s status=%s chunks=%s min_dims=%s max_dims=%s' % row, flush=True)
    for row in connection.execute('SELECT status,count(*) FROM chat_requests GROUP BY status ORDER BY status'):
        print('chat_status=%s count=%s' % row, flush=True)
