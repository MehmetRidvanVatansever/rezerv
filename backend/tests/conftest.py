"""
pytest fixture'ları:
- app: her test icin sifirdan, in-memory SQLite ile bir Flask app
- client: o app'in test client'i
- auth_client: onceden kayit olup giris yapmis bir client (ayrica user bilgisini de dondurur)
- diger_auth_client: ikinci, farkli bir kullanici ile giris yapmis client (sahiplik testleri icin)
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from app import create_app
from app.db import init_db


def gelecek_hafta_ici(saat=10, gun_ekle=1):
    """Testlerin her zaman calisabilmesi icin: bugunden en az `gun_ekle` gun
    sonraki ilk hafta ici (Pazartesi-Cuma) gunu, UTC 'saat:00' olarak dondurur.
    V-4 (hafta ici) ve V-6 (gecmis tarih olamaz) kurallarini otomatik karsilar."""
    gun = datetime.now(timezone.utc) + timedelta(days=gun_ekle)
    while gun.weekday() >= 5:  # 5=Cumartesi, 6=Pazar
        gun += timedelta(days=1)
    return gun.replace(hour=saat, minute=0, second=0, microsecond=0)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def app():
    # NOT: ":memory:" KULLANMIYORUZ. get_db() her app/request context'inde
    # yeni bir sqlite3.connect() acar; ":memory:" ile her connection ayri,
    # bos bir veritabani olusturur ("no such table" hatasi verir). Bunun
    # yerine her test icin gercek, gecici bir dosya DB'si kullaniyoruz.
    db_fd, db_path = tempfile.mkstemp()

    app = create_app(test_config={
        "TESTING": True,
        "DATABASE": db_path,
    })

    with app.app_context():
        init_db()

    yield app

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


def _register_and_login(client, email, password="Sifre123!", ad_soyad="Test Kullanici", departman="IT"):
    client.post("/auth/register", json={
        "ad_soyad": ad_soyad,
        "departman": departman,
        "email": email,
        "password": password,
    })
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp


@pytest.fixture
def auth_client(client):
    """Kayitli + giris yapmis bir kullanici ile client dondurur."""
    _register_and_login(client, "kullanici1@calik.com")
    return client


@pytest.fixture
def diger_auth_client(app):
    """Ayni app uzerinde IKINCI, farkli bir client+kullanici (kendi cookie jar'i ile)."""
    ikinci_client = app.test_client()
    _register_and_login(ikinci_client, "kullanici2@calik.com")
    return ikinci_client


@pytest.fixture
def admin_client(app):
    """Kayit olup giris yapmis, sonra veritabaninda role='admin' olarak
    manuel isaretlenmis bir kullanici (gercek ortamdaki admin atama
    yontemiyle ayni: 'UPDATE users SET role = admin WHERE email = ...')."""
    admin = app.test_client()
    _register_and_login(admin, "admin@calik.com")

    with app.app_context():
        from app.db import get_db
        db = get_db()
        db.execute("UPDATE users SET role = 'admin' WHERE email = ?", ("admin@calik.com",))
        db.commit()

    return admin


@pytest.fixture
def ornek_oda(app):
    """Testler icin veritabanina dogrudan bir oda ekler, dict olarak dondurur."""
    with app.app_context():
        from app.db import get_db
        import json
        db = get_db()
        cur = db.execute(
            "INSERT INTO rooms (ad, konum, kapasite, ekipman, is_active) VALUES (?, ?, ?, ?, 1)",
            ("Toplanti Odasi A", "3. Kat", 6, json.dumps(["projeksiyon", "tv"])),
        )
        db.commit()
        room = db.execute("SELECT * FROM rooms WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(room)