"""
Kimlik Doğrulama Modülü (Auth Blueprint)

Bu modül, kullanıcı kayıt ve giriş süreçlerini yönetir.
Tüm hatalar errors.py üzerinden standart formatta döner.
"""

import functools
import re

from flask import Blueprint, request, session, g, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .errors import error_response, bad_request, unauthorized, forbidden
from .logging_config import logger

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
    """Girişsiz istekleri 401 ile reddeden decorator."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return unauthorized()
        return view(**kwargs)
    return wrapped_view


def admin_required(view):
    """Girişsizse 401, giriş yapmış ama admin değilse 403 döner.
    Admin rolü şu an için manuel olarak veritabanında atanır:
        UPDATE users SET role = 'admin' WHERE email = '...';
    """
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return unauthorized()
        if g.user["role"] != "admin":
            return forbidden("Bu işlem için admin yetkisi gerekli.")
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
        return bad_request("Tüm alanlar zorunludur.")

    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        return bad_request("Geçersiz e-posta formatı.")

    if len(password) < 8:
        return bad_request("Şifre en az 8 karakter olmalı.")
    if not re.search(r"[A-Z]", password):
        return bad_request("Şifre en az bir büyük harf içermeli.")
    if not re.search(r"[a-z]", password):
        return bad_request("Şifre en az bir küçük harf içermeli.")
    if not re.search(r"[0-9]", password):
        return bad_request("Şifre en az bir rakam içermeli.")
    if not re.search(r"[!@#$%^&*()_\-+=\[\]{};:'\",.<>/?\\|`~]", password):
        return bad_request("Şifre en az bir özel karakter içermeli.")

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (ad_soyad, departman, email, password_hash) VALUES (?, ?, ?, ?)",
            (ad_soyad, departman, email, generate_password_hash(password)),
        )
        db.commit()
    except db.IntegrityError:
        return bad_request("Bu e-posta zaten kayıtlı.")

    logger.info(f"Yeni kullanıcı kaydı: email={email} departman={departman}")
    return jsonify({"message": "Kayıt başarılı."}), 201


@bp.route("/login", methods=("POST",))
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return bad_request("E-posta ve şifre zorunludur.")

    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()

    if user is None or not check_password_hash(user["password_hash"], password):
        logger.warning(f"Başarısız giriş denemesi: email={email}")
        return unauthorized("Geçersiz e-posta veya şifre.")

    session.clear()
    session["user_id"] = user["id"]
    logger.info(f"Giriş başarılı: user_id={user['id']} email={email}")
    return jsonify({
        "message": "Giriş başarılı.",
        "user": {
            "id": user["id"],
            "ad_soyad": user["ad_soyad"],
            "departman": user["departman"],
            "role": user["role"],
        },
    })


@bp.route("/logout", methods=("POST",))
def logout():
    if g.user is not None:
        logger.info(f"Çıkış yapıldı: user_id={g.user['id']}")
    session.clear()
    return jsonify({"message": "Çıkış yapıldı."})