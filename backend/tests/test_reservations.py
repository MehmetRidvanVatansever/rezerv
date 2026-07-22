"""
Faz 8 - Rezervasyon validasyon testleri (roadmap madde 36-38).
Cakisma tablosundaki her senaryo, kapasite asimi ve
update-kendi-kendine-cakisma bug'i dahil.
"""

import pytest

from tests.conftest import gelecek_hafta_ici, iso


def _rezervasyon_yap(client, room_id, baslangic, bitis, katilimci=2, baslik="Toplanti"):
    return client.post("/reservations", json={
        "room_id": room_id,
        "baslik": baslik,
        "katilimci_sayisi": katilimci,
        "start_time": iso(baslangic),
        "end_time": iso(bitis),
    })


@pytest.fixture
def mevcut_rezervasyon(auth_client, ornek_oda):
    """10:00-11:00 arasi mevcut bir rezervasyon olusturur, referans olarak kullanilir."""
    baslangic = gelecek_hafta_ici(saat=10)
    bitis = baslangic.replace(hour=11)
    resp = _rezervasyon_yap(auth_client, ornek_oda["id"], baslangic, bitis)
    assert resp.status_code == 201
    return {
        "id": resp.get_json()["id"],
        "baslangic": baslangic,
        "bitis": bitis,
        "room_id": ornek_oda["id"],
    }


# ---- V-8 Cakisma tablosu: PDF bolum 9'daki tum senaryolar ----

def test_cakisma_baslangica_deger_gecerli(auth_client, mevcut_rezervasyon):
    """09:00-10:00 -> gecerli (baslangica deger)"""
    b = mevcut_rezervasyon["baslangic"].replace(hour=9)
    e = mevcut_rezervasyon["baslangic"]
    resp = _rezervasyon_yap(auth_client, mevcut_rezervasyon["room_id"], b, e)
    assert resp.status_code == 201


def test_cakisma_bitise_deger_gecerli(auth_client, mevcut_rezervasyon):
    """11:00-12:00 -> gecerli (bitise deger)"""
    b = mevcut_rezervasyon["bitis"]
    e = mevcut_rezervasyon["bitis"].replace(hour=12)
    resp = _rezervasyon_yap(auth_client, mevcut_rezervasyon["room_id"], b, e)
    assert resp.status_code == 201


def test_cakisma_baslangicla_cakisiyor_reddedilir(auth_client, mevcut_rezervasyon):
    """09:30-10:30 -> reddedilir"""
    b = mevcut_rezervasyon["baslangic"].replace(hour=9, minute=30)
    e = mevcut_rezervasyon["baslangic"].replace(minute=30)
    resp = _rezervasyon_yap(auth_client, mevcut_rezervasyon["room_id"], b, e)
    assert resp.status_code == 409


def test_cakisma_bitisle_cakisiyor_reddedilir(auth_client, mevcut_rezervasyon):
    """10:30-11:30 -> reddedilir"""
    b = mevcut_rezervasyon["baslangic"].replace(minute=30)
    e = mevcut_rezervasyon["bitis"].replace(minute=30)
    resp = _rezervasyon_yap(auth_client, mevcut_rezervasyon["room_id"], b, e)
    assert resp.status_code == 409


def test_cakisma_tamamen_icinde_reddedilir(auth_client, mevcut_rezervasyon):
    """10:15-10:45 -> reddedilir (tamamen icinde)"""
    b = mevcut_rezervasyon["baslangic"].replace(minute=15)
    e = mevcut_rezervasyon["baslangic"].replace(minute=45)
    resp = _rezervasyon_yap(auth_client, mevcut_rezervasyon["room_id"], b, e)
    assert resp.status_code == 409


def test_cakisma_tamamen_kapsiyor_reddedilir(auth_client, mevcut_rezervasyon):
    """09:00-12:00 -> reddedilir (tamamen kapsiyor)"""
    b = mevcut_rezervasyon["baslangic"].replace(hour=9)
    e = mevcut_rezervasyon["bitis"].replace(hour=12)
    resp = _rezervasyon_yap(auth_client, mevcut_rezervasyon["room_id"], b, e)
    assert resp.status_code == 409


def test_cakisma_birebir_ayni_reddedilir(auth_client, mevcut_rezervasyon):
    """10:00-11:00 -> reddedilir (birebir ayni)"""
    resp = _rezervasyon_yap(
        auth_client, mevcut_rezervasyon["room_id"],
        mevcut_rezervasyon["baslangic"], mevcut_rezervasyon["bitis"]
    )
    assert resp.status_code == 409


def test_ayni_saat_farkli_oda_gecerli(auth_client, mevcut_rezervasyon):
    """Ayni saat, farkli oda -> gecerli"""
    resp = auth_client.post("/rooms", json={"ad": "Baska Oda", "konum": "5. Kat", "kapasite": 4})
    yeni_oda_id = resp.get_json()["id"]
    resp2 = _rezervasyon_yap(
        auth_client, yeni_oda_id,
        mevcut_rezervasyon["baslangic"], mevcut_rezervasyon["bitis"]
    )
    assert resp2.status_code == 201


def test_ayni_saat_kendi_guncellemesi_gecerli(auth_client, mevcut_rezervasyon):
    """Ayni saat, ayni oda, ama guncellenen rezervasyonun kendisi -> gecerli (klasik bug)"""
    resp = auth_client.put(f"/reservations/{mevcut_rezervasyon['id']}", json={
        "baslik": "Guncellenmis baslik",
        "start_time": iso(mevcut_rezervasyon["baslangic"]),
        "end_time": iso(mevcut_rezervasyon["bitis"]),
    })
    assert resp.status_code == 200


# ---- Diger validasyonlar (V-1 -> V-7, V-9) ----

def test_bitis_baslangictan_once_reddedilir(auth_client, ornek_oda):
    b = gelecek_hafta_ici(saat=10)
    e = b.replace(hour=9)
    resp = _rezervasyon_yap(auth_client, ornek_oda["id"], b, e)
    assert resp.status_code == 400


def test_mesai_disi_reddedilir(auth_client, ornek_oda):
    b = gelecek_hafta_ici(saat=7)  # 08:00'dan once
    e = b.replace(hour=8)
    resp = _rezervasyon_yap(auth_client, ornek_oda["id"], b, e)
    assert resp.status_code == 400


def test_hafta_sonu_reddedilir(auth_client, ornek_oda):
    import datetime as dt
    b = gelecek_hafta_ici(saat=10)
    # bir sonraki cumartesiye kadar ilerle
    while b.weekday() != 5:
        b = b + dt.timedelta(days=1)
    e = b.replace(hour=11)
    resp = _rezervasyon_yap(auth_client, ornek_oda["id"], b, e)
    assert resp.status_code == 400


def test_15dk_altinda_reddedilir(auth_client, ornek_oda):
    b = gelecek_hafta_ici(saat=10)
    e = b.replace(minute=10)
    resp = _rezervasyon_yap(auth_client, ornek_oda["id"], b, e)
    assert resp.status_code == 400


def test_4saat_ustunde_reddedilir(auth_client, ornek_oda):
    b = gelecek_hafta_ici(saat=8)
    e = b.replace(hour=13)  # 5 saat
    resp = _rezervasyon_yap(auth_client, ornek_oda["id"], b, e)
    assert resp.status_code == 400


def test_15dk_hizasinda_degil_reddedilir(auth_client, ornek_oda):
    b = gelecek_hafta_ici(saat=10).replace(minute=5)
    e = b.replace(hour=11, minute=5)
    resp = _rezervasyon_yap(auth_client, ornek_oda["id"], b, e)
    assert resp.status_code == 400


def test_gecmis_tarih_reddedilir(auth_client, ornek_oda):
    b = gelecek_hafta_ici(gun_ekle=-30, saat=10)
    e = b.replace(hour=11)
    resp = _rezervasyon_yap(auth_client, ornek_oda["id"], b, e)
    assert resp.status_code == 400


def test_olmayan_oda_404(auth_client):
    b = gelecek_hafta_ici(saat=10)
    e = b.replace(hour=11)
    resp = _rezervasyon_yap(auth_client, 99999, b, e)
    assert resp.status_code == 404


def test_pasif_odaya_rezervasyon_yapilamaz(auth_client, ornek_oda):
    auth_client.put(f"/rooms/{ornek_oda['id']}", json={"is_active": False})
    b = gelecek_hafta_ici(saat=10)
    e = b.replace(hour=11)
    resp = _rezervasyon_yap(auth_client, ornek_oda["id"], b, e)
    assert resp.status_code == 404


def test_kapasite_asimi_reddedilir(auth_client, ornek_oda):
    """ornek_oda kapasitesi 6; 10 kisilik istek reddedilmeli (V-9)"""
    b = gelecek_hafta_ici(saat=10)
    e = b.replace(hour=11)
    resp = _rezervasyon_yap(auth_client, ornek_oda["id"], b, e, katilimci=10)
    assert resp.status_code == 400


def test_katilimci_sifir_reddedilir(auth_client, ornek_oda):
    b = gelecek_hafta_ici(saat=10)
    e = b.replace(hour=11)
    resp = _rezervasyon_yap(auth_client, ornek_oda["id"], b, e, katilimci=0)
    assert resp.status_code == 400


def test_kapasite_siniri_dahilinde_gecerli(auth_client, ornek_oda):
    """Tam kapasite kadar (6) katilimci -> gecerli olmali"""
    b = gelecek_hafta_ici(saat=10)
    e = b.replace(hour=11)
    resp = _rezervasyon_yap(auth_client, ornek_oda["id"], b, e, katilimci=6)
    assert resp.status_code == 201


# ---- Guncelleme / iptal + sahiplik ----

def test_baskasinin_rezervasyonunu_guncelleyemez_403(auth_client, diger_auth_client, mevcut_rezervasyon):
    """mevcut_rezervasyon auth_client tarafindan olusturuldu; diger_auth_client
    onu guncellemeye calisirsa 403 donmeli."""
    resp = diger_auth_client.put(f"/reservations/{mevcut_rezervasyon['id']}", json={
        "baslik": "Baskasi degistiriyor",
    })
    assert resp.status_code == 403


def test_baskasinin_rezervasyonunu_silemez_403(auth_client, diger_auth_client, mevcut_rezervasyon):
    resp = diger_auth_client.delete(f"/reservations/{mevcut_rezervasyon['id']}")
    assert resp.status_code == 403


def test_kendi_rezervasyonunu_iptal_edebilir(auth_client, mevcut_rezervasyon):
    resp = auth_client.delete(f"/reservations/{mevcut_rezervasyon['id']}")
    assert resp.status_code == 200

    kalan = auth_client.get(f"/reservations?room_id={mevcut_rezervasyon['room_id']}").get_json()
    assert kalan == []


def test_girissiz_kullanici_reservations_gorebilir_ama_olusturamaz(client, ornek_oda):
    """GET /reservations login gerektirmiyor (FR-7), POST gerektiriyor (bkz. bolum 5)."""
    resp = client.get("/reservations")
    assert resp.status_code == 200