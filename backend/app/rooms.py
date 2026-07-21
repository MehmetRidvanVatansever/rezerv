"""
Oda Yönetimi Modülü (Rooms Blueprint)

- GET    /rooms       -> tüm aktif odaları listeler
- POST   /rooms       -> yeni oda oluşturur (giriş yapmış kullanıcı yeterli)
- PUT    /rooms/<id>  -> oda bilgilerini günceller (giriş yapmış kullanıcı yeterli)
- DELETE /rooms/<id>  -> odayı pasife alır (silmez); gelecekteki rezervasyonu
                         varsa işlemi reddeder
"""
import json
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from .auth import login_required
from .db import get_db

bp = Blueprint("rooms", __name__, url_prefix="/rooms")


def room_to_dict(row):
    return {
        "id": row["id"],
        "ad": row["ad"],
        "konum": row["konum"],
        "kapasite": row["kapasite"],
        "ekipman": json.loads(row["ekipman"]) if row["ekipman"] else [],
        "is_active": bool(row["is_active"]),
    }


@bp.route("", methods=("GET",))
def list_rooms():
    db = get_db()
    rooms = db.execute(
        "SELECT * FROM rooms WHERE is_active = 1 ORDER BY ad"
    ).fetchall()
    return jsonify([room_to_dict(r) for r in rooms])


@bp.route("", methods=("POST",))
@login_required
def create_room():
    data = request.get_json() or {}

    ad = data.get("ad")
    konum = data.get("konum")
    kapasite = data.get("kapasite")
    ekipman = data.get("ekipman", [])

    if not all([ad, konum]) or kapasite is None:
        return jsonify({"error": "ad, konum ve kapasite zorunludur."}), 400

    if not isinstance(kapasite, int) or kapasite <= 0:
        return jsonify({"error": "Kapasite pozitif bir tam sayı olmalı."}), 400

    if not isinstance(ekipman, list):
        return jsonify({"error": "Ekipman bir liste olmalı, örn: [\"projektor\", \"tv\"]."}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO rooms (ad, konum, kapasite, ekipman, is_active) VALUES (?, ?, ?, ?, 1)",
        (ad, konum, kapasite, json.dumps(ekipman, ensure_ascii=False)),
    )
    db.commit()

    room = db.execute("SELECT * FROM rooms WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(room_to_dict(room)), 201


@bp.route("/<int:room_id>", methods=("PUT",))
@login_required
def update_room(room_id):
    db = get_db()
    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None:
        return jsonify({"error": "Oda bulunamadı."}), 404

    data = request.get_json() or {}

    ad = data.get("ad", room["ad"])
    konum = data.get("konum", room["konum"])
    kapasite = data.get("kapasite", room["kapasite"])
    ekipman = data.get("ekipman", json.loads(room["ekipman"]) if room["ekipman"] else [])
    is_active = data.get("is_active", bool(room["is_active"]))

    if not isinstance(kapasite, int) or kapasite <= 0:
        return jsonify({"error": "Kapasite pozitif bir tam sayı olmalı."}), 400

    if not isinstance(ekipman, list):
        return jsonify({"error": "Ekipman bir liste olmalı, örn: [\"projektor\", \"tv\"]."}), 400

    db.execute(
        "UPDATE rooms SET ad = ?, konum = ?, kapasite = ?, ekipman = ?, is_active = ? WHERE id = ?",
        (ad, konum, kapasite, json.dumps(ekipman, ensure_ascii=False), int(bool(is_active)), room_id),
    )
    db.commit()

    updated = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    return jsonify(room_to_dict(updated))


@bp.route("/<int:room_id>", methods=("DELETE",))
@login_required
def delete_room(room_id):
    db = get_db()
    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None:
        return jsonify({"error": "Oda bulunamadı."}), 404

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    upcoming = db.execute(
        "SELECT COUNT(*) AS c FROM reservations WHERE room_id = ? AND end_time > ?",
        (room_id, now_iso),
    ).fetchone()["c"]

    if upcoming > 0:
        return jsonify({
            "error": "conflict",
            "message": "Bu odaya ait gelecekteki rezervasyonlar var, önce onları iptal edin.",
            "details": {"upcoming_reservations": upcoming},
        }), 409

    db.execute("UPDATE rooms SET is_active = 0 WHERE id = ?", (room_id,))
    db.commit()
    return jsonify({"message": "Oda pasife alındı."})