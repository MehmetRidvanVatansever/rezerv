"""
Kimlik Doğrulama Modülü (Auth Blueprint)

Bu modül, kullanıcı kayıt ve giriş süreçlerini yönetir:
- /register: Yeni kullanıcı kaydı oluşturur, şifreleri hash'ler ve veritabanına kaydeder.
- /login: Kullanıcı kimlik doğrulamasını yapar ve oturum (session) başlatır.
- Güvenlik: Şifreleme için 'werkzeug.security' (hash), oturum yönetimi için 'session' kullanılır.
- Veri Formatı: İletişim tamamen JSON üzerinden gerçekleştirilir.
"""
import functools
import re

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, jsonify
)
from werkzeug.security import check_password_hash, generate_password_hash
from .db import get_db

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.before_app_request
def load_logged_in_user():
    """Her istekten önce session'daki user_id'yi g.user'a yükler."""
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def login_required(view):
    """Girişsiz istekleri 401 ile reddeden decorator. Diğer blueprint'lerde
    (rooms, reservations) korumalı endpoint'lerin üzerine eklenir."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return jsonify({"error": "unauthorized", "message": "Giriş yapmanız gerekiyor."}), 401
        return view(**kwargs)

    return wrapped_view


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@bp.route("/register", methods=("POST",))
def register():
    data = request.get_json()

    ad_soyad = data.get("ad_soyad")
    departman = data.get("departman")
    email = data.get("email")
    password = data.get("password")

    if not all([ad_soyad, departman, email, password]):
        return jsonify({"error": "Tüm alanlar zorunludur."}), 400

    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Geçersiz e-posta formatı."}), 400

    if len(password) < 8:
        return jsonify({"error": "Şifre en az 8 karakter olmalı."}), 400
    if not re.search(r"[A-Z]", password):
        return jsonify({"error": "Şifre en az bir büyük harf içermeli."}), 400
    if not re.search(r"[a-z]", password):
        return jsonify({"error": "Şifre en az bir küçük harf içermeli."}), 400
    if not re.search(r"[0-9]", password):
        return jsonify({"error": "Şifre en az bir rakam içermeli."}), 400
    if not re.search(r"[!@#$%^&*()_\-+=\[\]{};:'\",.<>/?\\|`~]", password):
        return jsonify({"error": "Şifre en az bir özel karakter içermeli."}), 400

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (ad_soyad, departman, email, password_hash) VALUES (?, ?, ?, ?)",
            (ad_soyad, departman, email, generate_password_hash(password)),
        )
        db.commit()
    except db.IntegrityError:
        return jsonify({"error": "Bu e-posta zaten kayıtlı."}), 400

    return jsonify({"message": "Kayıt başarılı."}), 201


@bp.route("/login", methods=("POST",))
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()

    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Geçersiz e-posta veya şifre."}), 401

    session.clear()
    session["user_id"] = user["id"]
    return jsonify({"message": "Giriş başarılı.", "user": user["ad_soyad"]})


@bp.route("/logout", methods=("POST",))
def logout():
    """Session'ı temizler, kullanıcıyı çıkış yaptırır."""
    session.clear()
    return jsonify({"message": "Çıkış yapıldı."})