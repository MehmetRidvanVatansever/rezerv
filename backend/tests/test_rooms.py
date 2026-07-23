"""
Faz 8/güncelleme - Oda CRUD + admin yetkilendirme testleri.

Değişiklikler:
- Oda oluşturma/güncelleme/pasifleştirme/aktifleştirme artık sadece admin.
- DELETE /rooms/<id> kaldırıldı; artık sadece deactivate/reactivate var.
- GET /rooms artık aktif + pasif TÜM odaları döner.
- Favori oda toggle + listeleme.
"""


def test_oda_listeleme_bos(client):
    resp = client.get("/rooms")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_oda_olusturma_girissiz_401(client):
    resp = client.post("/rooms", json={"ad": "Oda 1", "konum": "1. Kat", "kapasite": 4})
    assert resp.status_code == 401


def test_oda_olusturma_normal_kullanici_403(auth_client):
    """Giris yapmis ama admin olmayan kullanici oda olusturamaz."""
    resp = auth_client.post("/rooms", json={"ad": "Oda 1", "konum": "1. Kat", "kapasite": 4})
    assert resp.status_code == 403


def test_oda_olusturma_ve_listeleme_admin(admin_client):
    resp = admin_client.post("/rooms", json={
        "ad": "Toplanti Odasi B", "konum": "2. Kat", "kapasite": 8, "ekipman": ["tv"]
    })
    assert resp.status_code == 201

    resp2 = admin_client.get("/rooms")
    odalar = resp2.get_json()
    assert len(odalar) == 1
    assert odalar[0]["ad"] == "Toplanti Odasi B"
    assert odalar[0]["is_active"] is True


def test_oda_guncelleme_normal_kullanici_403(auth_client, ornek_oda):
    resp = auth_client.put(f"/rooms/{ornek_oda['id']}", json={"kapasite": 12})
    assert resp.status_code == 403


def test_oda_guncelleme_admin(admin_client, ornek_oda):
    resp = admin_client.put(f"/rooms/{ornek_oda['id']}", json={"kapasite": 12})
    assert resp.status_code == 200
    assert resp.get_json()["kapasite"] == 12


def test_delete_endpoint_artik_yok(admin_client, ornek_oda):
    """DELETE /rooms/<id> kaldirildi; admin bile olsa 404/405 donmeli (route yok)."""
    resp = admin_client.delete(f"/rooms/{ornek_oda['id']}")
    assert resp.status_code in (404, 405)


def test_pasiflestirme_girissiz_401(client, ornek_oda):
    resp = client.post(f"/rooms/{ornek_oda['id']}/deactivate")
    assert resp.status_code == 401


def test_pasiflestirme_normal_kullanici_403(auth_client, ornek_oda):
    resp = auth_client.post(f"/rooms/{ornek_oda['id']}/deactivate")
    assert resp.status_code == 403


def test_pasiflestirme_admin(admin_client, ornek_oda):
    resp = admin_client.post(f"/rooms/{ornek_oda['id']}/deactivate")
    assert resp.status_code == 200
    assert resp.get_json()["is_active"] is False


def test_pasif_oda_hala_listede_gorunur(admin_client, ornek_oda):
    """GET /rooms artik aktif+pasif hepsini donuyor, pasif oda listeden kaybolmamali."""
    admin_client.post(f"/rooms/{ornek_oda['id']}/deactivate")

    odalar = admin_client.get("/rooms").get_json()
    ilgili = [o for o in odalar if o["id"] == ornek_oda["id"]]
    assert len(ilgili) == 1
    assert ilgili[0]["is_active"] is False


def test_aktiflestirme_admin(admin_client, ornek_oda):
    admin_client.post(f"/rooms/{ornek_oda['id']}/deactivate")
    resp = admin_client.post(f"/rooms/{ornek_oda['id']}/reactivate")
    assert resp.status_code == 200
    assert resp.get_json()["is_active"] is True


def test_aktiflestirme_normal_kullanici_403(auth_client, admin_client, ornek_oda):
    admin_client.post(f"/rooms/{ornek_oda['id']}/deactivate")
    resp = auth_client.post(f"/rooms/{ornek_oda['id']}/reactivate")
    assert resp.status_code == 403


def test_olmayan_oda_pasiflestirme_404(admin_client):
    resp = admin_client.post("/rooms/99999/deactivate")
    assert resp.status_code == 404


# ---- Favori odalar ----

def test_favori_ekle_ve_listele(auth_client, ornek_oda):
    resp = auth_client.post(f"/rooms/{ornek_oda['id']}/favorite")
    assert resp.status_code == 200
    assert resp.get_json()["favorited"] is True

    favoriler = auth_client.get("/rooms/favorites").get_json()
    assert len(favoriler) == 1
    assert favoriler[0]["id"] == ornek_oda["id"]


def test_favori_toggle_kaldirir(auth_client, ornek_oda):
    auth_client.post(f"/rooms/{ornek_oda['id']}/favorite")  # ekle
    resp = auth_client.post(f"/rooms/{ornek_oda['id']}/favorite")  # tekrar -> kaldir
    assert resp.status_code == 200
    assert resp.get_json()["favorited"] is False

    favoriler = auth_client.get("/rooms/favorites").get_json()
    assert favoriler == []


def test_favori_girissiz_401(client, ornek_oda):
    resp = client.post(f"/rooms/{ornek_oda['id']}/favorite")
    assert resp.status_code == 401


def test_favoriler_kullaniciya_ozeldir(auth_client, diger_auth_client, ornek_oda):
    """kullanici1 favoriye ekler, kullanici2'nin favori listesinde gorunmemeli."""
    auth_client.post(f"/rooms/{ornek_oda['id']}/favorite")

    kullanici2_favoriler = diger_auth_client.get("/rooms/favorites").get_json()
    assert kullanici2_favoriler == []