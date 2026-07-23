"""
Seed Script

Bu script, rooms.json dosyasindaki gercek oda verisini (Calik Enerji ofis
gezisiyle toplanan envanter) rooms tablosuna yukler.

Kullanim (backend/ dizininden calistirilmali):
    flask --app main init-db      # once semayi kur (varsa uzerine yazmaz)
    python -m seeds.seed_rooms    # odalari yukle / guncelle

Not: 'ad' alani ayirt edici anahtar olarak kullanilir. Ayni isimde bir oda
zaten varsa kaydı SILMEZ, sadece konum/kapasite/ekipman alanlarini
rooms.json ile es zamanlar (upsert). Boylece rooms.json'da yapilan bir
guncelleme (orn. ekipman listesi eklenmesi) script tekrar calistirildiginda
mevcut kayitlara da yansir; is_active durumu ve o odaya bagli
rezervasyonlar korunur.
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

        eklenen, guncellenen = 0, 0
        for room in rooms:
            ekipman_json = json.dumps(room.get("ekipman", []), ensure_ascii=False)
            existing = db.execute(
                "SELECT id FROM rooms WHERE ad = ?", (room["ad"],)
            ).fetchone()

            if existing:
                db.execute(
                    "UPDATE rooms SET konum = ?, kapasite = ?, ekipman = ? WHERE id = ?",
                    (room["konum"], room["kapasite"], ekipman_json, existing["id"]),
                )
                guncellenen += 1
            else:
                db.execute(
                    "INSERT INTO rooms (ad, konum, kapasite, ekipman, is_active) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        room["ad"],
                        room["konum"],
                        room["kapasite"],
                        ekipman_json,
                        int(bool(room.get("is_active", True))),
                    ),
                )
                eklenen += 1

        db.commit()
        print(f"Seed tamamlandi: {eklenen} oda eklendi, {guncellenen} oda guncellendi.")


if __name__ == "__main__":
    seed_rooms()