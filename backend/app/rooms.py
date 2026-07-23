"""
Oda Yönetimi Modülü (Rooms Blueprint)

- GET    /rooms                 -> tüm odaları listeler (aktif + pasif)
- POST   /rooms                 -> yeni oda oluşturur (sadece admin)
- PUT    /rooms/<id>            -> oda bilgilerini günceller (sadece admin)
- POST   /rooms/<id>/deactivate -> odayı pasifleştirir (sadece admin)
- POST   /rooms/<id>/reactivate -> odayı aktif eder (sadece admin)
- POST   /rooms/<id>/favorite   -> giriş yapmış kullanıcı için favori toggle
- GET    /rooms/favorites       -> giriş yapmış kullanıcının favori odaları

NOT: DELETE /rooms/<id> kaldırıldı. Odalar artık hiçbir zaman gerçekten
silinmiyor, sadece is_active alanı ile pasifleştirilip aktif edilebiliyor.
"""

import json

from flask import Blueprint, request, jsonify, g

from .auth import login_required, admin_required
from .db import get_db
from .errors import error_response, bad_request, not_found, conflict

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
    """Tüm odaları döner (aktif + pasif). Frontend, is_active alanına
    bakarak pasif odaları farklı gösterebilir."""
    db = get_db()
    rooms = db.execute("SELECT * FROM rooms ORDER BY ad").fetchall()
    return jsonify([room_to_dict(r) for r in rooms])


@bp.route("", methods=("POST",))
@admin_required
def create_room():
    data = request.get_json() or {}

    ad = data.get("ad")
    konum = data.get("konum")
    kapasite = data.get("kapasite")
    ekipman = data.get("ekipman", [])

    if not all([ad, konum]) or kapasite is None:
        return bad_request("ad, konum ve kapasite zorunludur.")

    if not isinstance(kapasite, int) or kapasite <= 0:
        return bad_request("Kapasite pozitif bir tam sayı olmalı.")

    if not isinstance(ekipman, list):
        return bad_request("Ekipman bir liste olmalı, örn: [\"projektor\", \"tv\"].")

    db = get_db()
    cur = db.execute(
        "INSERT INTO rooms (ad, konum, kapasite, ekipman, is_active) VALUES (?, ?, ?, ?, 1)",
        (ad, konum, kapasite, json.dumps(ekipman, ensure_ascii=False)),
    )
    db.commit()

    room = db.execute("SELECT * FROM rooms WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(room_to_dict(room)), 201


@bp.route("/<int:room_id>", methods=("PUT",))
@admin_required
def update_room(room_id):
    db = get_db()
    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None:
        return not_found("Oda bulunamadı.")

    data = request.get_json() or {}

    ad = data.get("ad", room["ad"])
    konum = data.get("konum", room["konum"])
    kapasite = data.get("kapasite", room["kapasite"])
    ekipman = data.get("ekipman", json.loads(room["ekipman"]) if room["ekipman"] else [])
    is_active = data.get("is_active", bool(room["is_active"]))

    if not isinstance(kapasite, int) or kapasite <= 0:
        return bad_request("Kapasite pozitif bir tam sayı olmalı.")

    if not isinstance(ekipman, list):
        return bad_request("Ekipman bir liste olmalı.")

    db.execute(
        "UPDATE rooms SET ad = ?, konum = ?, kapasite = ?, ekipman = ?, is_active = ? WHERE id = ?",
        (ad, konum, kapasite, json.dumps(ekipman, ensure_ascii=False), int(bool(is_active)), room_id),
    )
    db.commit()

    updated = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    return jsonify(room_to_dict(updated))


@bp.route("/<int:room_id>/deactivate", methods=("POST",))
@admin_required
def deactivate_room(room_id):
    db = get_db()
    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None:
        return not_found("Oda bulunamadı.")

    db.execute("UPDATE rooms SET is_active = 0 WHERE id = ?", (room_id,))
    db.commit()

    updated = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    return jsonify(room_to_dict(updated))


@bp.route("/<int:room_id>/reactivate", methods=("POST",))
@admin_required
def reactivate_room(room_id):
    db = get_db()
    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None:
        return not_found("Oda bulunamadı.")

    db.execute("UPDATE rooms SET is_active = 1 WHERE id = ?", (room_id,))
    db.commit()

    updated = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    return jsonify(room_to_dict(updated))


@bp.route("/favorites", methods=("GET",))
@login_required
def list_favorites():
    db = get_db()
    rows = db.execute(
        """SELECT rooms.* FROM favorite_rooms
           JOIN rooms ON rooms.id = favorite_rooms.room_id
           WHERE favorite_rooms.user_id = ?
           ORDER BY favorite_rooms.created_at DESC""",
        (g.user["id"],),
    ).fetchall()
    return jsonify([room_to_dict(r) for r in rows])


@bp.route("/<int:room_id>/favorite", methods=("POST",))
@login_required
def toggle_favorite(room_id):
    db = get_db()
    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None:
        return not_found("Oda bulunamadı.")

    existing = db.execute(
        "SELECT id FROM favorite_rooms WHERE user_id = ? AND room_id = ?",
        (g.user["id"], room_id),
    ).fetchone()

    if existing is not None:
        db.execute("DELETE FROM favorite_rooms WHERE id = ?", (existing["id"],))
        db.commit()
        return jsonify({"room_id": room_id, "favorited": False})

    db.execute(
        "INSERT INTO favorite_rooms (user_id, room_id) VALUES (?, ?)",
        (g.user["id"], room_id),
    )
    db.commit()
    return jsonify({"room_id": room_id, "favorited": True})