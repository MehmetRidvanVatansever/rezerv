"""
Admin İstatistik Modülü (Admin Blueprint)

Tüm endpoint'ler sadece role='admin' olan kullanıcılar tarafından
erişilebilir (admin_required decorator).

- GET /admin/stats/overview        -> genel özet
- GET /admin/stats/rooms           -> en çok/en az kullanılan odalar
- GET /admin/stats/departments     -> departman istatistikleri
- GET /admin/stats/time            -> saat aralığı + gün bazlı yoğunluk
- GET /admin/stats/user/<user_id>  -> kullanıcı bazlı istatistik

NOT: İptal edilen rezervasyonlar veritabanından tamamen silindiği için
(hard-delete), "iptal sayısı" gibi bir istatistik burada YOK — mevcut
şemayla bu veri tutulmuyor.
"""

from flask import Blueprint, jsonify

from .auth import admin_required
from .db import get_db
from .errors import not_found

bp = Blueprint("admin", __name__, url_prefix="/admin/stats")

GUN_ADLARI = {
    "0": "Pazar",
    "1": "Pazartesi",
    "2": "Salı",
    "3": "Çarşamba",
    "4": "Perşembe",
    "5": "Cuma",
    "6": "Cumartesi",
}


@bp.route("/overview", methods=("GET",))
@admin_required
def overview():
    db = get_db()

    toplam_kullanici = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    aktif_oda = db.execute("SELECT COUNT(*) AS c FROM rooms WHERE is_active = 1").fetchone()["c"]
    pasif_oda = db.execute("SELECT COUNT(*) AS c FROM rooms WHERE is_active = 0").fetchone()["c"]
    toplam_rezervasyon = db.execute("SELECT COUNT(*) AS c FROM reservations").fetchone()["c"]

    bugunku = db.execute(
        "SELECT COUNT(*) AS c FROM reservations WHERE date(start_time) = date('now')"
    ).fetchone()["c"]

    # "Bu hafta" = son 7 gün (takvim haftası değil, kayan pencere)
    son_7_gun = db.execute(
        "SELECT COUNT(*) AS c FROM reservations WHERE date(start_time) >= date('now', '-6 days')"
    ).fetchone()["c"]

    return jsonify({
        "toplam_kullanici": toplam_kullanici,
        "aktif_oda_sayisi": aktif_oda,
        "pasif_oda_sayisi": pasif_oda,
        "toplam_rezervasyon": toplam_rezervasyon,
        "bugunku_rezervasyon_sayisi": bugunku,
        "son_7_gun_rezervasyon_sayisi": son_7_gun,
    })


@bp.route("/rooms", methods=("GET",))
@admin_required
def rooms_stats():
    db = get_db()
    rows = db.execute(
        """SELECT rooms.id, rooms.ad, rooms.konum, rooms.is_active,
                  COUNT(reservations.id) AS rezervasyon_sayisi
           FROM rooms
           LEFT JOIN reservations ON reservations.room_id = rooms.id
           GROUP BY rooms.id
           ORDER BY rezervasyon_sayisi DESC"""
    ).fetchall()

    odalar = [
        {
            "id": r["id"],
            "ad": r["ad"],
            "konum": r["konum"],
            "is_active": bool(r["is_active"]),
            "rezervasyon_sayisi": r["rezervasyon_sayisi"],
        }
        for r in rows
    ]

    return jsonify({
        "tum_odalar": odalar,
        "en_cok_kullanilan": odalar[:5],
        "en_az_kullanilan": list(reversed(odalar))[:5],
    })


@bp.route("/departments", methods=("GET",))
@admin_required
def departments_stats():
    db = get_db()
    rows = db.execute(
        """SELECT users.departman,
                  COUNT(DISTINCT users.id) AS kullanici_sayisi,
                  COUNT(reservations.id) AS rezervasyon_sayisi
           FROM users
           LEFT JOIN reservations ON reservations.user_id = users.id
           GROUP BY users.departman
           ORDER BY rezervasyon_sayisi DESC"""
    ).fetchall()

    return jsonify([
        {
            "departman": r["departman"],
            "kullanici_sayisi": r["kullanici_sayisi"],
            "rezervasyon_sayisi": r["rezervasyon_sayisi"],
        }
        for r in rows
    ])


@bp.route("/time", methods=("GET",))
@admin_required
def time_stats():
    db = get_db()

    # Saat aralığı yoğunluğu (start_time = "...THH:MM:SSZ" -> HH kısmı)
    saat_satirlari = db.execute(
        """SELECT substr(start_time, 12, 2) AS saat, COUNT(*) AS sayi
           FROM reservations
           GROUP BY saat
           ORDER BY sayi DESC"""
    ).fetchall()

    # Haftanın günü yoğunluğu (%w: 0=Pazar ... 6=Cumartesi)
    gun_satirlari = db.execute(
        """SELECT strftime('%w', start_time) AS gun_no, COUNT(*) AS sayi
           FROM reservations
           GROUP BY gun_no
           ORDER BY sayi DESC"""
    ).fetchall()

    saat_yogunlugu = [
        {"saat": f"{r['saat']}:00", "sayi": r["sayi"]} for r in saat_satirlari
    ]
    gun_yogunlugu = [
        {"gun": GUN_ADLARI.get(r["gun_no"], r["gun_no"]), "sayi": r["sayi"]}
        for r in gun_satirlari
    ]

    return jsonify({
        "saat_yogunlugu": saat_yogunlugu,
        "en_yogun_saat": saat_yogunlugu[0] if saat_yogunlugu else None,
        "gun_yogunlugu": gun_yogunlugu,
        "en_yogun_gun": gun_yogunlugu[0] if gun_yogunlugu else None,
    })


@bp.route("/user/<int:user_id>", methods=("GET",))
@admin_required
def user_stats(user_id):
    db = get_db()

    user = db.execute(
        "SELECT id, ad_soyad, departman, email FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if user is None:
        return not_found("Kullanıcı bulunamadı.")

    genel = db.execute(
        """SELECT COUNT(*) AS toplam,
                  AVG((julianday(end_time) - julianday(start_time)) * 24 * 60) AS ort_sure_dk
           FROM reservations WHERE user_id = ?""",
        (user_id,),
    ).fetchone()

    en_cok_kullandigi_oda = db.execute(
        """SELECT rooms.id, rooms.ad, COUNT(reservations.id) AS sayi
           FROM reservations
           JOIN rooms ON rooms.id = reservations.room_id
           WHERE reservations.user_id = ?
           GROUP BY rooms.id
           ORDER BY sayi DESC
           LIMIT 1""",
        (user_id,),
    ).fetchone()

    ort_sure = genel["ort_sure_dk"]

    return jsonify({
        "user_id": user["id"],
        "ad_soyad": user["ad_soyad"],
        "departman": user["departman"],
        "toplam_rezervasyon": genel["toplam"],
        "ortalama_toplanti_suresi_dk": round(ort_sure, 1) if ort_sure is not None else None,
        "en_cok_kullandigi_oda": (
            {"id": en_cok_kullandigi_oda["id"], "ad": en_cok_kullandigi_oda["ad"],
             "sayi": en_cok_kullandigi_oda["sayi"]}
            if en_cok_kullandigi_oda is not None else None
        ),
    })