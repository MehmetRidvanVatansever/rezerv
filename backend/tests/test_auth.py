"""Faz 8 - Auth testleri (roadmap madde 34)."""


def test_register_basarili(client):
    resp = client.post("/auth/register", json={
        "ad_soyad": "Ali Veli",
        "departman": "Muhendislik",
        "email": "ali@calik.com",
        "password": "Sifre123!",
    })
    assert resp.status_code == 201


def test_register_zayif_sifre_reddedilir(client):
    resp = client.post("/auth/register", json={
        "ad_soyad": "Ali Veli",
        "departman": "Muhendislik",
        "email": "ali2@calik.com",
        "password": "1234",  # kurallara uymuyor: kisa, buyuk harf/ozel karakter yok
    })
    assert resp.status_code == 400


def test_register_ayni_email_iki_kez_olamaz(client):
    payload = {
        "ad_soyad": "Ali Veli",
        "departman": "IT",
        "email": "tekrar@calik.com",
        "password": "Sifre123!",
    }
    r1 = client.post("/auth/register", json=payload)
    r2 = client.post("/auth/register", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 400


def test_login_basarili(client):
    client.post("/auth/register", json={
        "ad_soyad": "Ayse Yilmaz",
        "departman": "Finans",
        "email": "ayse@calik.com",
        "password": "Sifre123!",
    })
    resp = client.post("/auth/login", json={"email": "ayse@calik.com", "password": "Sifre123!"})
    assert resp.status_code == 200


def test_login_yanlis_sifre_401(client):
    client.post("/auth/register", json={
        "ad_soyad": "Ayse Yilmaz",
        "departman": "Finans",
        "email": "ayse2@calik.com",
        "password": "Sifre123!",
    })
    resp = client.post("/auth/login", json={"email": "ayse2@calik.com", "password": "yanlissifre"})
    assert resp.status_code == 401


def test_girissiz_rezervasyon_olusturma_401(client, ornek_oda):
    """Yetkilendirilmis endpoint'e girissiz istek -> 401."""
    resp = client.post("/reservations", json={
        "room_id": ornek_oda["id"],
        "baslik": "Toplanti",
        "katilimci_sayisi": 2,
        "start_time": "2099-01-05T10:00:00Z",
        "end_time": "2099-01-05T11:00:00Z",
    })
    assert resp.status_code == 401


def test_logout(auth_client):
    resp = auth_client.post("/auth/logout")
    assert resp.status_code == 200
    # cikis sonrasi tekrar korumali endpoint'e istek 401 donmeli
    resp2 = auth_client.post("/reservations", json={})
    assert resp2.status_code == 401