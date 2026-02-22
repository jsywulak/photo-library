"""
searcher.py — photo search logic.

search() queries photos that match any of the given tags, ranked by how many
of the searched tags each photo has. Photos with no matching tags are excluded.
"""


def search(tags: list[str], db_conn) -> list[dict]:
    normalised = [t.strip().lower() for t in tags]
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.s3_key, COUNT(pt.tag_id) AS match_count
            FROM photos p
            JOIN photo_tags pt ON pt.photo_id = p.id
            JOIN tags t        ON t.id = pt.tag_id
            WHERE t.name = ANY(%s)
            GROUP BY p.id, p.s3_key
            ORDER BY match_count DESC
            """,
            (normalised,),
        )
        return [
            {"s3_key": row[0], "match_count": row[1]}
            for row in cur.fetchall()
        ]
