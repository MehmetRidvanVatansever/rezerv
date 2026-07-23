"""
Rezervasyon Modülü (Reservations Blueprint)

Tüm validasyonlar ve hatalar standart error_response ile döner.

Zaman formatı kararı: Tüm start_time/end_time değerleri UTC'de,
timezone-aware olarak işlenir ve veritabanına ISO 8601 + 'Z' formatında
("2026-07-20T13:00:00Z") saklanır. Bu sayede sunucunun çalıştığı yerel
saat dilimi hesaba karışmaz ve "geçmiş tarih" (V-6) kontrolü tutarlı
kalır. Client'tan gelen değer offset içermiyorsa (ör. "2026-07-20T13:00:00")
UTC olduğu varsayılır.
"""

import json
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, g

from .auth import login_required
from .db import get_db
from .errors import error_response, bad_request, not_found, conflict, forbidden, unauthorized
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
    """ISO 8601 string'i UTC, timezone-aware bir datetime'a çevirir.
    Offset/'Z' yoksa UTC varsayılır. Geçersizse None döner."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def to_storage_str(dt):
    """UTC datetime'ı DB'de saklanacak ISO 8601 + Z string'ine çevirir."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_reservation_fields(room_id, katilimci_sayisi, start, end, db):
    """Ortak validasyon zinciri (V-1 -> V-9, sıralı). Hata varsa
    (response, None) döner; her şey geçerliyse (None, room) döner."""

    # V-1: end > start
    if end <= start:
        return bad_request("Bitiş saati başlangıçtan sonra olmalı."), None

    # V-2: aynı gün içinde (UTC gününe göre)
    if start.date() != end.date():
        return bad_request("Rezervasyon aynı gün içinde olmalı."), None

    # V-3: 08:00-18:00 aralığında
    calisma_baslangic = start.replace(hour=CALISMA_BASLANGIC, minute=0, second=0, microsecond=0)
    calisma_bitis = start.replace(hour=CALISMA_BITIS, minute=0, second=0, microsecond=0)
    if start < calisma_baslangic or end > calisma_bitis:
        return bad_request(f"Rezervasyon {CALISMA_BASLANGIC:02d}:00-{CALISMA_BITIS:02d}:00 aralığında olmalı."), None

    # V-4: sadece hafta içi
    if start.weekday() >= 5:
        return bad_request("Rezervasyon sadece hafta içi yapılabilir."), None

    # V-5: süre kontrolü
    sure_dk = (end - start).total_seconds() / 60
    if sure_dk < MIN_SURE_DK or sure_dk > MAX_SURE_DK:
        return bad_request(f"Süre {MIN_SURE_DK} dakika ile {MAX_SURE_DK // 60} saat arasında olmalı."), None
    if sure_dk % MIN_SURE_DK != 0 or start.minute % MIN_SURE_DK != 0:
        return bad_request("Başlangıç ve süre 15 dakikaya hizalı olmalı (örn: 09:00, 09:15...)."), None

    # V-6: geçmiş tarihe rezervasyon yok (UTC 'şimdi' ile karşılaştır)
    if start < datetime.now(timezone.utc):
        return bad_request("Geçmiş bir tarihe rezervasyon yapılamaz."), None

    # V-7: oda var ve aktif mi
    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None or not room["is_active"]:
        return not_found("Oda bulunamadı veya aktif değil."), None

    # V-9 (tip kontrolü burada, kapasite karşılaştırması çağıran yerde yapılır)
    if not isinstance(katilimci_sayisi, int) or katilimci_sayisi < 1:
        return bad_request("Katılımcı sayısı en az 1 olmalı."), None

    return None, room


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
        return bad_request("start_time/end_time ISO 8601 formatında olmalı, örn: 2026-07-22T10:00:00Z")

    db = get_db()

    err, room = _validate_reservation_fields(room_id, katilimci_sayisi, start, end, db)
    if err is not None:
        return err

    # V-8: çakışma kontrolü
    conflict_row = db.execute(
        """SELECT id FROM reservations
           WHERE room_id = ? AND start_time < ? AND end_time > ?""",
        (room_id, to_storage_str(end), to_storage_str(start)),
    ).fetchone()
    if conflict_row is not None:
        logger.warning(
            f"Çakışma reddi: user_id={g.user['id']} room_id={room_id} "
            f"start={to_storage_str(start)} end={to_storage_str(end)} "
            f"cakisan_rezervasyon_id={conflict_row['id']}"
        )
        return conflict(
            "Bu oda seçilen saat aralığında zaten dolu.",
            {"conflicting_reservation_id": conflict_row["id"]}
        )

    # V-9: kapasite kontrolü
    if katilimci_sayisi > room["kapasite"]:
        logger.warning(
            f"Kapasite reddi: user_id={g.user['id']} room_id={room_id} "
            f"katilimci_sayisi={katilimci_sayisi} oda_kapasitesi={room['kapasite']}"
        )
        return bad_request(f"Bu oda en fazla {room['kapasite']} kişilik.")

    cur = db.execute(
        """INSERT INTO reservations (room_id, user_id, baslik, katilimci_sayisi, start_time, end_time)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (room_id, g.user["id"], baslik, katilimci_sayisi, to_storage_str(start), to_storage_str(end)),
    )
    db.commit()

    logger.info(
        f"Rezervasyon oluşturuldu: id={cur.lastrowid} user_id={g.user['id']} "
        f"room_id={room_id} start={to_storage_str(start)} end={to_storage_str(end)}"
    )

    reservation = db.execute("SELECT * FROM reservations WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(reservation_to_dict(reservation)), 201


@bp.route("", methods=("GET",))
def list_reservations():
    room_id = request.args.get("room_id")
    date_str = request.args.get("date")
    mine = request.args.get("mine")

    query = "SELECT * FROM reservations WHERE 1=1"
    params = []

    if room_id:
        query += " AND room_id = ?"
        params.append(room_id)

    if date_str:
        query += " AND date(start_time) = ?"
        params.append(date_str)

    if mine == "true":
        if g.user is None:
            return unauthorized()
        query += " AND user_id = ?"
        params.append(g.user["id"])

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

    # Sahiplik kontrolü: yalnızca rezervasyonu oluşturan kullanıcı düzenleyebilir
    if existing["user_id"] != g.user["id"]:
        logger.warning(
            f"Yetkisiz güncelleme denemesi: user_id={g.user['id']} "
            f"reservation_id={reservation_id} sahibi={existing['user_id']}"
        )
        return forbidden("Bu rezervasyonu yalnızca sahibi düzenleyebilir.")

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

    err, room = _validate_reservation_fields(room_id, katilimci_sayisi, start, end, db)
    if err is not None:
        return err

    # Çakışma kontrolü (kendi rezervasyonu hariç)
    conflict_row = db.execute(
        """SELECT id FROM reservations
           WHERE room_id = ? AND id != ? AND start_time < ? AND end_time > ?""",
        (room_id, reservation_id, to_storage_str(end), to_storage_str(start)),
    ).fetchone()
    if conflict_row is not None:
        logger.warning(
            f"Çakışma reddi (güncelleme): user_id={g.user['id']} reservation_id={reservation_id} "
            f"room_id={room_id} start={to_storage_str(start)} end={to_storage_str(end)} "
            f"cakisan_rezervasyon_id={conflict_row['id']}"
        )
        return conflict(
            "Bu oda seçilen saat aralığında zaten dolu.",
            {"conflicting_reservation_id": conflict_row["id"]}
        )

    if katilimci_sayisi > room["kapasite"]:
        logger.warning(
            f"Kapasite reddi (güncelleme): user_id={g.user['id']} reservation_id={reservation_id} "
            f"room_id={room_id} katilimci_sayisi={katilimci_sayisi} oda_kapasitesi={room['kapasite']}"
        )
        return bad_request(f"Bu oda en fazla {room['kapasite']} kişilik.")

    db.execute(
        """UPDATE reservations SET room_id = ?, baslik = ?, katilimci_sayisi = ?,
           start_time = ?, end_time = ? WHERE id = ?""",
        (room_id, baslik, katilimci_sayisi, to_storage_str(start), to_storage_str(end), reservation_id),
    )
    db.commit()

    logger.info(
        f"Rezervasyon güncellendi: id={reservation_id} user_id={g.user['id']} "
        f"room_id={room_id} start={to_storage_str(start)} end={to_storage_str(end)}"
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

    # Sahiplik kontrolü: yalnızca rezervasyonu oluşturan kullanıcı iptal edebilir
    if existing["user_id"] != g.user["id"]:
        logger.warning(
            f"Yetkisiz iptal denemesi: user_id={g.user['id']} "
            f"reservation_id={reservation_id} sahibi={existing['user_id']}"
        )
        return forbidden("Bu rezervasyonu yalnızca sahibi iptal edebilir.")

    db.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))
    db.commit()
    logger.info(f"Rezervasyon iptal edildi: id={reservation_id} user_id={g.user['id']}")
    return jsonify({"message": "Rezervasyon iptal edildi."})