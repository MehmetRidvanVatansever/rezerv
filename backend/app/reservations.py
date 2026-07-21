"""
Rezervasyon Modülü (Reservations Blueprint)

- POST   /reservations       -> yeni rezervasyon oluşturur (V-1..V-9 sırasıyla kontrol edilir)
- GET    /reservations       -> oda ve/veya tarihe göre filtreleyerek listeler
- PUT    /reservations/<id>  -> günceller (kendisiyle çakışma saymaz)
- DELETE /reservations/<id>  -> iptal eder

Zaman formatı: ISO 8601, 'YYYY-MM-DDTHH:MM:SS' (saniyesiz de kabul edilir).
Bu proje tek ofis/tek saat dilimi için tasarlandığı için zaman değerleri
UTC'ye çevrilmeden, TR yerel saati olarak "naive" (tz'siz) saklanır -
schema.sql'deki örnek yorum UTC dese de mesai saati/hafta içi
kontrollerinin basit kalması için yerel saat kullanıyoruz. Çok ofisli/
çok saat dilimli bir kurulumda bu karar değişmeli.
"""
import json
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request, g

from .auth import login_required
from .db import get_db

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
        return jsonify({"error": "invalid_input", "message": "room_id, baslik, katilimci_sayisi, start_time, end_time zorunludur."}), 400

    start = parse_iso(start_raw)
    end = parse_iso(end_raw)
    if start is None or end is None:
        return jsonify({"error": "invalid_input", "message": "start_time/end_time ISO 8601 formatında olmalı, örn: 2026-07-22T10:00:00"}), 400

    # V-1: end > start
    if end <= start:
        return jsonify({"error": "invalid_range", "message": "Bitiş saati başlangıçtan sonra olmalı."}), 400

    # V-2: aynı gün içinde
    if start.date() != end.date():
        return jsonify({"error": "invalid_range", "message": "Rezervasyon aynı gün içinde olmalı."}), 400

    # V-3: 08:00-18:00 aralığında
    calisma_baslangic = start.replace(hour=CALISMA_BASLANGIC, minute=0, second=0, microsecond=0)
    calisma_bitis = start.replace(hour=CALISMA_BITIS, minute=0, second=0, microsecond=0)
    if start < calisma_baslangic or end > calisma_bitis:
        return jsonify({"error": "outside_hours", "message": f"Rezervasyon {CALISMA_BASLANGIC:02d}:00-{CALISMA_BITIS:02d}:00 aralığında olmalı."}), 400

    # V-4: sadece hafta içi (0=Pazartesi ... 6=Pazar)
    if start.weekday() >= 5:
        return jsonify({"error": "weekend", "message": "Rezervasyon sadece hafta içi yapılabilir."}), 400

    # V-5: süre 15dk-4saat, 15dk'ya hizalı
    sure_dk = (end - start).total_seconds() / 60
    if sure_dk < MIN_SURE_DK or sure_dk > MAX_SURE_DK:
        return jsonify({"error": "invalid_duration", "message": f"Süre {MIN_SURE_DK} dakika ile {MAX_SURE_DK // 60} saat arasında olmalı."}), 400
    if sure_dk % MIN_SURE_DK != 0 or start.minute % MIN_SURE_DK != 0:
        return jsonify({"error": "invalid_duration", "message": "Başlangıç ve süre 15 dakikaya hizalı olmalı (örn: 09:00, 09:15, 09:30...)."}), 400

    # V-6: geçmiş tarihe rezervasyon yok
    if start < datetime.now():
        return jsonify({"error": "past_date", "message": "Geçmiş bir tarihe rezervasyon yapılamaz."}), 400

    db = get_db()

    # V-7: oda var ve aktif mi
    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None or not room["is_active"]:
        return jsonify({"error": "room_not_found", "message": "Oda bulunamadı veya aktif değil."}), 404

    # V-8: çakışma kontrolü — yeni.start < mevcut.end VE yeni.end > mevcut.start
    conflict = db.execute(
        """SELECT id FROM reservations
           WHERE room_id = ? AND start_time < ? AND end_time > ?""",
        (room_id, end.isoformat(), start.isoformat()),
    ).fetchone()
    if conflict is not None:
        return jsonify({
            "error": "conflict",
            "message": "Bu oda seçilen saat aralığında zaten dolu.",
            "details": {"conflicting_reservation_id": conflict["id"]},
        }), 409

    # V-9: kapasite kontrolü
    if not isinstance(katilimci_sayisi, int) or katilimci_sayisi < 1:
        return jsonify({"error": "invalid_input", "message": "Katılımcı sayısı en az 1 olmalı."}), 400
    if katilimci_sayisi > room["kapasite"]:
        return jsonify({
            "error": "capacity_exceeded",
            "message": f"Bu oda en fazla {room['kapasite']} kişilik.",
        }), 400

    cur = db.execute(
        """INSERT INTO reservations (room_id, user_id, baslik, katilimci_sayisi, start_time, end_time)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (room_id, g.user["id"], baslik, katilimci_sayisi, start.isoformat(), end.isoformat()),
    )
    db.commit()

    reservation = db.execute("SELECT * FROM reservations WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(reservation_to_dict(reservation)), 201


@bp.route("", methods=("GET",))
def list_reservations():
    room_id = request.args.get("room_id")
    date_str = request.args.get("date")  # YYYY-MM-DD

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
        return jsonify({"error": "not_found", "message": "Rezervasyon bulunamadı."}), 404

    data = request.get_json() or {}

    room_id = data.get("room_id", existing["room_id"])
    baslik = data.get("baslik", existing["baslik"])
    katilimci_sayisi = data.get("katilimci_sayisi", existing["katilimci_sayisi"])
    start_raw = data.get("start_time", existing["start_time"])
    end_raw = data.get("end_time", existing["end_time"])

    start = parse_iso(start_raw)
    end = parse_iso(end_raw)
    if start is None or end is None:
        return jsonify({"error": "invalid_input", "message": "start_time/end_time ISO 8601 formatında olmalı."}), 400

    if end <= start:
        return jsonify({"error": "invalid_range", "message": "Bitiş saati başlangıçtan sonra olmalı."}), 400
    if start.date() != end.date():
        return jsonify({"error": "invalid_range", "message": "Rezervasyon aynı gün içinde olmalı."}), 400

    calisma_baslangic = start.replace(hour=CALISMA_BASLANGIC, minute=0, second=0, microsecond=0)
    calisma_bitis = start.replace(hour=CALISMA_BITIS, minute=0, second=0, microsecond=0)
    if start < calisma_baslangic or end > calisma_bitis:
        return jsonify({"error": "outside_hours", "message": f"Rezervasyon {CALISMA_BASLANGIC:02d}:00-{CALISMA_BITIS:02d}:00 aralığında olmalı."}), 400

    if start.weekday() >= 5:
        return jsonify({"error": "weekend", "message": "Rezervasyon sadece hafta içi yapılabilir."}), 400

    sure_dk = (end - start).total_seconds() / 60
    if sure_dk < MIN_SURE_DK or sure_dk > MAX_SURE_DK:
        return jsonify({"error": "invalid_duration", "message": f"Süre {MIN_SURE_DK} dakika ile {MAX_SURE_DK // 60} saat arasında olmalı."}), 400
    if sure_dk % MIN_SURE_DK != 0 or start.minute % MIN_SURE_DK != 0:
        return jsonify({"error": "invalid_duration", "message": "Başlangıç ve süre 15 dakikaya hizalı olmalı."}), 400

    if start < datetime.now():
        return jsonify({"error": "past_date", "message": "Geçmiş bir tarihe rezervasyon yapılamaz."}), 400

    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None or not room["is_active"]:
        return jsonify({"error": "room_not_found", "message": "Oda bulunamadı veya aktif değil."}), 404

    # çakışma kontrolü — kendi id'si hariç (WHERE id != kendi_id)
    conflict = db.execute(
        """SELECT id FROM reservations
           WHERE room_id = ? AND id != ? AND start_time < ? AND end_time > ?""",
        (room_id, reservation_id, end.isoformat(), start.isoformat()),
    ).fetchone()
    if conflict is not None:
        return jsonify({
            "error": "conflict",
            "message": "Bu oda seçilen saat aralığında zaten dolu.",
            "details": {"conflicting_reservation_id": conflict["id"]},
        }), 409

    if not isinstance(katilimci_sayisi, int) or katilimci_sayisi < 1:
        return jsonify({"error": "invalid_input", "message": "Katılımcı sayısı en az 1 olmalı."}), 400
    if katilimci_sayisi > room["kapasite"]:
        return jsonify({
            "error": "capacity_exceeded",
            "message": f"Bu oda en fazla {room['kapasite']} kişilik.",
        }), 400

    db.execute(
        """UPDATE reservations SET room_id = ?, baslik = ?, katilimci_sayisi = ?,
           start_time = ?, end_time = ? WHERE id = ?""",
        (room_id, baslik, katilimci_sayisi, start.isoformat(), end.isoformat(), reservation_id),
    )
    db.commit()

    updated = db.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,)).fetchone()
    return jsonify(reservation_to_dict(updated))


@bp.route("/<int:reservation_id>", methods=("DELETE",))
@login_required
def delete_reservation(reservation_id):
    db = get_db()
    existing = db.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,)).fetchone()
    if existing is None:
        return jsonify({"error": "not_found", "message": "Rezervasyon bulunamadı."}), 404

    db.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))
    db.commit()
    return jsonify({"message": "Rezervasyon iptal edildi."})