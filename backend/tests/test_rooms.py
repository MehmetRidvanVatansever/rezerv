"""Faz 8 - Oda CRUD testleri (roadmap madde 35, FR-1/2/3)."""

from tests.conftest import gelecek_hafta_ici, iso


def test_oda_listeleme_bos(client):
    resp = client.get("/rooms")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_oda_olusturma_girissiz_401(client):
    resp = client.post("/rooms", json={"ad": "Oda 1", "konum": "1. Kat", "kapasite": 4})
    assert resp.status_code == 401


def test_oda_olusturma_ve_listeleme(auth_client):
    resp = auth_client.post("/rooms", json={
        "ad": "Toplanti Odasi B", "konum": "2. Kat", "kapasite": 8, "ekipman": ["tv"]
    })
    assert resp.status_code == 201

    resp2 = auth_client.get("/rooms")
    odalar = resp2.get_json()
    assert len(odalar) == 1
    assert odalar[0]["ad"] == "Toplanti Odasi B"
    assert odalar[0]["is_active"] is True


def test_oda_guncelleme(auth_client, ornek_oda):
    resp = auth_client.put(f"/rooms/{ornek_oda['id']}", json={"kapasite": 12})
    assert resp.status_code == 200
    assert resp.get_json()["kapasite"] == 12


def test_gelecek_rezervasyonu_olan_oda_silinemez_pasife_alinir(auth_client, ornek_oda):
    baslangic = gelecek_hafta_ici()
    bitis = baslangic.replace(hour=baslangic.hour + 1)
    auth_client.post("/reservations", json={
        "room_id": ornek_oda["id"],
        "baslik": "Onemli toplanti",
        "katilimci_sayisi": 2,
        "start_time": iso(baslangic),
        "end_time": iso(bitis),
    })

    resp = auth_client.delete(f"/rooms/{ornek_oda['id']}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["deactivated"] is True

    # Oda artik aktif listede gorunmemeli (soft-delete)
    odalar = auth_client.get("/rooms").get_json()
    assert all(o["id"] != ornek_oda["id"] for o in odalar)


def test_gelecek_rezervasyonu_olmayan_oda_gercekten_silinir(auth_client, ornek_oda):
    resp = auth_client.delete(f"/rooms/{ornek_oda['id']}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["deleted"] is True