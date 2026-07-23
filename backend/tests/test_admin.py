"""
Adim 2 - Admin istatistik endpoint testleri.
Tum endpoint'ler sadece role='admin' kullanicilar icin.
"""

import json

from tests.conftest import gelecek_hafta_ici, iso


def _rezervasyon_ekle(client, room_id, saat=10, gun_ekle=1, sure_saat=1):
    b = gelecek_hafta_ici(saat=saat, gun_ekle=gun_ekle)
    e = b.replace(hour=b.hour + sure_saat)
    return client.post("/reservations", json={
        "room_id": room_id, "baslik": "Toplanti", "katilimci_sayisi": 2,
        "start_time": iso(b), "end_time": iso(e),
    })


# ---- Yetkilendirme: her endpoint icin girissiz/normal-kullanici/admin ----

def test_stats_girissiz_401(client):
    assert client.get("/admin/stats/overview").status_code == 401
    assert client.get("/admin/stats/rooms").status_code == 401
    assert client.get("/admin/stats/departments").status_code == 401
    assert client.get("/admin/stats/time").status_code == 401
    assert client.get("/admin/stats/user/1").status_code == 401


def test_stats_normal_kullanici_403(auth_client):
    assert auth_client.get("/admin/stats/overview").status_code == 403
    assert auth_client.get("/admin/stats/rooms").status_code == 403
    assert auth_client.get("/admin/stats/departments").status_code == 403
    assert auth_client.get("/admin/stats/time").status_code == 403
    assert auth_client.get("/admin/stats/user/1").status_code == 403


# ---- Overview ----

def test_overview_bos_sistem(admin_client):
    resp = admin_client.get("/admin/stats/overview")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["toplam_rezervasyon"] == 0
    assert body["toplam_kullanici"] >= 1  # en az admin'in kendisi


def test_overview_rezervasyon_sayisi_dogru(admin_client, ornek_oda):
    _rezervasyon_ekle(admin_client, ornek_oda["id"])
    body = admin_client.get("/admin/stats/overview").get_json()
    assert body["toplam_rezervasyon"] == 1
    assert body["son_7_gun_rezervasyon_sayisi"] == 1


# ---- Rooms ----

def test_rooms_stats_kullanim_sirasi(app, admin_client, ornek_oda):
    with app.app_context():
        from app.db import get_db
        db = get_db()
        cur = db.execute(
            "INSERT INTO rooms (ad, konum, kapasite, ekipman, is_active) VALUES (?,?,?,?,1)",
            ("Az Kullanilan Oda", "9. Kat", 4, json.dumps([])),
        )
        db.commit()
        az_kullanilan_id = cur.lastrowid

    # ornek_oda 2 kez, digeri hic kullanilmiyor
    _rezervasyon_ekle(admin_client, ornek_oda["id"], gun_ekle=1)
    _rezervasyon_ekle(admin_client, ornek_oda["id"], gun_ekle=8)

    resp = admin_client.get("/admin/stats/rooms").get_json()
    assert resp["en_cok_kullanilan"][0]["id"] == ornek_oda["id"]
    assert resp["en_cok_kullanilan"][0]["rezervasyon_sayisi"] == 2

    az_kullanilan_idler = [o["id"] for o in resp["en_az_kullanilan"]]
    assert az_kullanilan_id in az_kullanilan_idler


# ---- Departments ----

def test_departments_stats(admin_client, auth_client, ornek_oda):
    """auth_client fixture'i 'IT' departmaninda bir kullanici olusturuyor (conftest)."""
    _rezervasyon_ekle(auth_client, ornek_oda["id"])
    resp = admin_client.get("/admin/stats/departments").get_json()
    it_departmani = next((d for d in resp if d["departman"] == "IT"), None)
    assert it_departmani is not None
    assert it_departmani["rezervasyon_sayisi"] >= 1


# ---- Time ----

def test_time_stats_en_yogun_saat(admin_client, ornek_oda):
    _rezervasyon_ekle(admin_client, ornek_oda["id"], saat=14, gun_ekle=1)
    _rezervasyon_ekle(admin_client, ornek_oda["id"], saat=14, gun_ekle=8)
    _rezervasyon_ekle(admin_client, ornek_oda["id"], saat=9, gun_ekle=2)

    resp = admin_client.get("/admin/stats/time").get_json()
    assert resp["en_yogun_saat"]["saat"] == "14:00"
    assert resp["en_yogun_saat"]["sayi"] == 2


def test_time_stats_bos_sistemde_none_doner(admin_client):
    resp = admin_client.get("/admin/stats/time").get_json()
    assert resp["en_yogun_saat"] is None
    assert resp["en_yogun_gun"] is None
    assert resp["saat_yogunlugu"] == []


# ---- User stats ----

def test_user_stats_olmayan_kullanici_404(admin_client):
    resp = admin_client.get("/admin/stats/user/99999")
    assert resp.status_code == 404


def test_user_stats_temel_bilgiler(app, admin_client, auth_client, ornek_oda):
    _rezervasyon_ekle(auth_client, ornek_oda["id"], saat=10, sure_saat=2)  # 120 dk

    with app.app_context():
        from app.db import get_db
        db = get_db()
        uid = db.execute("SELECT id FROM users WHERE email = ?", ("kullanici1@calik.com",)).fetchone()["id"]

    resp = admin_client.get(f"/admin/stats/user/{uid}").get_json()
    assert resp["toplam_rezervasyon"] == 1
    assert resp["ortalama_toplanti_suresi_dk"] == 120.0
    assert resp["en_cok_kullandigi_oda"]["id"] == ornek_oda["id"]
    assert resp["departman"] == "IT"


def test_user_stats_hic_rezervasyonu_olmayan_kullanici(app, admin_client):
    with app.app_context():
        from app.db import get_db
        db = get_db()
        admin_id = db.execute("SELECT id FROM users WHERE email = ?", ("admin@calik.com",)).fetchone()["id"]

    resp = admin_client.get(f"/admin/stats/user/{admin_id}").get_json()
    assert resp["toplam_rezervasyon"] == 0
    assert resp["ortalama_toplanti_suresi_dk"] is None
    assert resp["en_cok_kullandigi_oda"] is None