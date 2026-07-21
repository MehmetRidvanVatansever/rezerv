"""
Rezervasyon Modülü (Reservations Blueprint)

Tüm validasyonlar ve hatalar standart error_response ile döner.
"""

import json
from datetime import datetime

from flask import Blueprint, jsonify, request, g

from .auth import login_required
from .db import get_db
from .errors import error_response, bad_request, not_found, conflict
from .logging_config import logger

bp = Blueprint("reservations", __name__, url_prefix="/reservations")

CALISMA_BASLANGIC = 8   # 08:00
CALISMA_BITIS = 18      # 18:00
MIN_SURE_DK = 15
MAX_SURE_DK = 240        # 4 saat


def reservation_to_dict(row):
    return {
        "id": row["id"],
        "room_id": row["room_id"],
        "user_id": row["user_id"],
        "baslik": row["baslik"],
        "katilimci_sayisi": row["katilimci_sayisi"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "created_at": row["created_at"],
    }


def parse_iso(value):
    """ISO 8601 string'i datetime'a çevirir. Geçersizse None döner."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1]
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


@bp.route("", methods=("POST",))
@login_required
def create_reservation():
    data = request.get_json() or {}

    room_id = data.get("room_id")
    baslik = data.get("baslik")
    katilimci_sayisi = data.get("katilimci_sayisi")
    start_raw = data.get("start_time")
    end_raw = data.get("end_time")

    if not all([room_id, baslik, katilimci_sayisi, start_raw, end_raw]):
        return bad_request("room_id, baslik, katilimci_sayisi, start_time, end_time zorunludur.")

    start = parse_iso(start_raw)
    end = parse_iso(end_raw)
    if start is None or end is None:
        return bad_request("start_time/end_time ISO 8601 formatında olmalı, örn: 2026-07-22T10:00:00")

    # V-1: end > start
    if end <= start:
        return bad_request("Bitiş saati başlangıçtan sonra olmalı.")

    # V-2: aynı gün içinde
    if start.date() != end.date():
        return bad_request("Rezervasyon aynı gün içinde olmalı.")

    # V-3: 08:00-18:00 aralığında
    calisma_baslangic = start.replace(hour=CALISMA_BASLANGIC, minute=0, second=0, microsecond=0)
    calisma_bitis = start.replace(hour=CALISMA_BITIS, minute=0, second=0, microsecond=0)
    if start < calisma_baslangic or end > calisma_bitis:
        return bad_request(f"Rezervasyon {CALISMA_BASLANGIC:02d}:00-{CALISMA_BITIS:02d}:00 aralığında olmalı.")

    # V-4: sadece hafta içi
    if start.weekday() >= 5:
        return bad_request("Rezervasyon sadece hafta içi yapılabilir.")

    # V-5: süre kontrolü
    sure_dk = (end - start).total_seconds() / 60
    if sure_dk < MIN_SURE_DK or sure_dk > MAX_SURE_DK:
        return bad_request(f"Süre {MIN_SURE_DK} dakika ile {MAX_SURE_DK // 60} saat arasında olmalı.")
    if sure_dk % MIN_SURE_DK != 0 or start.minute % MIN_SURE_DK != 0:
        return bad_request("Başlangıç ve süre 15 dakikaya hizalı olmalı (örn: 09:00, 09:15...).")

    # V-6: geçmiş tarihe rezervasyon yok
    if start < datetime.now():
        return bad_request("Geçmiş bir tarihe rezervasyon yapılamaz.")

    db = get_db()

    # V-7: oda var ve aktif mi
    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None or not room["is_active"]:
        return not_found("Oda bulunamadı veya aktif değil.")

    # V-8: çakışma kontrolü
    conflict_row = db.execute(
        """SELECT id FROM reservations
           WHERE room_id = ? AND start_time < ? AND end_time > ?""",
        (room_id, end.isoformat(), start.isoformat()),
    ).fetchone()
    if conflict_row is not None:
        logger.warning(
            f"Çakışma reddi: user_id={g.user['id']} room_id={room_id} "
            f"start={start.isoformat()} end={end.isoformat()} "
            f"cakisan_rezervasyon_id={conflict_row['id']}"
        )
        return conflict(
            "Bu oda seçilen saat aralığında zaten dolu.",
            {"conflicting_reservation_id": conflict_row["id"]}
        )

    # V-9: kapasite kontrolü
    if not isinstance(katilimci_sayisi, int) or katilimci_sayisi < 1:
        return bad_request("Katılımcı sayısı en az 1 olmalı.")
    if katilimci_sayisi > room["kapasite"]:
        logger.warning(
            f"Kapasite reddi: user_id={g.user['id']} room_id={room_id} "
            f"katilimci_sayisi={katilimci_sayisi} oda_kapasitesi={room['kapasite']}"
        )
        return bad_request(f"Bu oda en fazla {room['kapasite']} kişilik.")

    cur = db.execute(
        """INSERT INTO reservations (room_id, user_id, baslik, katilimci_sayisi, start_time, end_time)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (room_id, g.user["id"], baslik, katilimci_sayisi, start.isoformat(), end.isoformat()),
    )
    db.commit()

    logger.info(
        f"Rezervasyon oluşturuldu: id={cur.lastrowid} user_id={g.user['id']} "
        f"room_id={room_id} start={start.isoformat()} end={end.isoformat()}"
    )

    reservation = db.execute("SELECT * FROM reservations WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(reservation_to_dict(reservation)), 201


@bp.route("", methods=("GET",))
def list_reservations():
    room_id = request.args.get("room_id")
    date_str = request.args.get("date")

    query = "SELECT * FROM reservations WHERE 1=1"
    params = []

    if room_id:
        query += " AND room_id = ?"
        params.append(room_id)

    if date_str:
        query += " AND date(start_time) = ?"
        params.append(date_str)

    query += " ORDER BY start_time"

    db = get_db()
    rows = db.execute(query, params).fetchall()
    return jsonify([reservation_to_dict(r) for r in rows])


@bp.route("/<int:reservation_id>", methods=("PUT",))
@login_required
def update_reservation(reservation_id):
    db = get_db()
    existing = db.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,)).fetchone()
    if existing is None:
        return not_found("Rezervasyon bulunamadı.")

    data = request.get_json() or {}

    room_id = data.get("room_id", existing["room_id"])
    baslik = data.get("baslik", existing["baslik"])
    katilimci_sayisi = data.get("katilimci_sayisi", existing["katilimci_sayisi"])
    start_raw = data.get("start_time", existing["start_time"])
    end_raw = data.get("end_time", existing["end_time"])

    start = parse_iso(start_raw)
    end = parse_iso(end_raw)
    if start is None or end is None:
        return bad_request("start_time/end_time ISO 8601 formatında olmalı.")

    if end <= start:
        return bad_request("Bitiş saati başlangıçtan sonra olmalı.")
    if start.date() != end.date():
        return bad_request("Rezervasyon aynı gün içinde olmalı.")

    calisma_baslangic = start.replace(hour=CALISMA_BASLANGIC, minute=0, second=0, microsecond=0)
    calisma_bitis = start.replace(hour=CALISMA_BITIS, minute=0, second=0, microsecond=0)
    if start < calisma_baslangic or end > calisma_bitis:
        return bad_request(f"Rezervasyon {CALISMA_BASLANGIC:02d}:00-{CALISMA_BITIS:02d}:00 aralığında olmalı.")

    if start.weekday() >= 5:
        return bad_request("Rezervasyon sadece hafta içi yapılabilir.")

    sure_dk = (end - start).total_seconds() / 60
    if sure_dk < MIN_SURE_DK or sure_dk > MAX_SURE_DK:
        return bad_request(f"Süre {MIN_SURE_DK} dakika ile {MAX_SURE_DK // 60} saat arasında olmalı.")
    if sure_dk % MIN_SURE_DK != 0 or start.minute % MIN_SURE_DK != 0:
        return bad_request("Başlangıç ve süre 15 dakikaya hizalı olmalı.")

    if start < datetime.now():
        return bad_request("Geçmiş bir tarihe rezervasyon yapılamaz.")

    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None or not room["is_active"]:
        return not_found("Oda bulunamadı veya aktif değil.")

    # Çakışma kontrolü (kendi rezervasyonu hariç)
    conflict_row = db.execute(
        """SELECT id FROM reservations
           WHERE room_id = ? AND id != ? AND start_time < ? AND end_time > ?""",
        (room_id, reservation_id, end.isoformat(), start.isoformat()),
    ).fetchone()
    if conflict_row is not None:
        logger.warning(
            f"Çakışma reddi (güncelleme): user_id={g.user['id']} reservation_id={reservation_id} "
            f"room_id={room_id} start={start.isoformat()} end={end.isoformat()} "
            f"cakisan_rezervasyon_id={conflict_row['id']}"
        )
        return conflict(
            "Bu oda seçilen saat aralığında zaten dolu.",
            {"conflicting_reservation_id": conflict_row["id"]}
        )

    if not isinstance(katilimci_sayisi, int) or katilimci_sayisi < 1:
        return bad_request("Katılımcı sayısı en az 1 olmalı.")
    if katilimci_sayisi > room["kapasite"]:
        logger.warning(
            f"Kapasite reddi (güncelleme): user_id={g.user['id']} reservation_id={reservation_id} "
            f"room_id={room_id} katilimci_sayisi={katilimci_sayisi} oda_kapasitesi={room['kapasite']}"
        )
        return bad_request(f"Bu oda en fazla {room['kapasite']} kişilik.")

    db.execute(
        """UPDATE reservations SET room_id = ?, baslik = ?, katilimci_sayisi = ?,
           start_time = ?, end_time = ? WHERE id = ?""",
        (room_id, baslik, katilimci_sayisi, start.isoformat(), end.isoformat(), reservation_id),
    )
    db.commit()

    logger.info(
        f"Rezervasyon güncellendi: id={reservation_id} user_id={g.user['id']} "
        f"room_id={room_id} start={start.isoformat()} end={end.isoformat()}"
    )

    updated = db.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,)).fetchone()
    return jsonify(reservation_to_dict(updated))


@bp.route("/<int:reservation_id>", methods=("DELETE",))
@login_required
def delete_reservation(reservation_id):
    db = get_db()
    existing = db.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,)).fetchone()
    if existing is None:
        return not_found("Rezervasyon bulunamadı.")

    db.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))
    db.commit()
    logger.info(f"Rezervasyon iptal edildi: id={reservation_id} user_id={g.user['id']}")
    return jsonify({"message": "Rezervasyon iptal edildi."})