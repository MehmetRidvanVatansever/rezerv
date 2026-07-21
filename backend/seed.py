"""
Seed Script

Bu script, rooms.json dosyasindaki gercek oda verisini (Calik Enerji ofis
gezisiyle toplanan envanter) rooms tablosuna yukler.

Kullanim:
    flask --app main init-db   # once semayi kur (varsa uzerine yazmaz)
    python seed.py              # odalari yukle

Not: id sutunu rooms.json'da referans amacli bulunur; veritabanina
AUTOINCREMENT ile tekrar id atanir, ayni 'ad' zaten varsa o kayit
atlanir (script tekrar tekrar guvenle calistirilabilir).
"""
import json
import os

from app import create_app
from app.db import get_db

ROOMS_FILE = os.path.join(os.path.dirname(__file__), "rooms.json")


def seed_rooms():
    app = create_app()
    with app.app_context():
        db = get_db()

        with open(ROOMS_FILE, encoding="utf-8") as f:
            rooms = json.load(f)

        eklenen, atlanan = 0, 0
        for room in rooms:
            exists = db.execute(
                "SELECT 1 FROM rooms WHERE ad = ?", (room["ad"],)
            ).fetchone()
            if exists:
                atlanan += 1
                continue

            db.execute(
                "INSERT INTO rooms (ad, konum, kapasite, ekipman, is_active) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    room["ad"],
                    room["konum"],
                    room["kapasite"],
                    json.dumps(room.get("ekipman", []), ensure_ascii=False),
                    int(bool(room.get("is_active", True))),
                ),
            )
            eklenen += 1

        db.commit()
        print(f"Seed tamamlandi: {eklenen} oda eklendi, {atlanan} oda zaten vardi (atlandi).")


if __name__ == "__main__":
    seed_rooms()