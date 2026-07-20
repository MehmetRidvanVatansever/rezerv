"""
Kimlik Doğrulama Modülü (Auth Blueprint)

Bu modül, kullanıcı kayıt ve giriş süreçlerini yönetir:
- /register: Yeni kullanıcı kaydı oluşturur, şifreleri hash'ler ve veritabanına kaydeder.
- /login: Kullanıcı kimlik doğrulamasını yapar ve oturum (session) başlatır.
- Güvenlik: Şifreleme için 'werkzeug.security' (hash), oturum yönetimi için 'session' kullanılır.
- Veri Formatı: İletişim tamamen JSON üzerinden gerçekleştirilir.
"""
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, jsonify
)
from werkzeug.security import check_password_hash, generate_password_hash
from .db import get_db

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/register", methods=("POST",))
def register():
    data = request.get_json()

    ad_soyad = data.get("ad_soyad")
    departman = data.get("departman")
    email = data.get("email")
    password = data.get("password")

    if not all([ad_soyad, departman, email, password]):
        return jsonify({"error": "Tüm alanlar zorunludur."}), 400

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