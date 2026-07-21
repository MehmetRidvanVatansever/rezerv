"""
Standart Hata Yanıt Modülü

Tüm endpoint'lerde tutarlı JSON hata formatı sağlar.
"""

from flask import jsonify


def error_response(error_code: str, message: str, status_code: int = 400, details: dict = None):
    """
    Standart hata yanıtı oluşturur.
    
    Örnek:
    {
        "error": "conflict",
        "message": "Bu oda seçilen saat aralığında zaten dolu.",
        "details": {"conflicting_reservation_id": 5}
    }
    """
    response = {
        "error": error_code,
        "message": message
    }
    
    if details is not None:
        response["details"] = details
        
    return jsonify(response), status_code


# Sık kullanılan hata kısayolları
def bad_request(message: str, details: dict = None):
    return error_response("invalid_input", message, 400, details)


def unauthorized(message: str = "Giriş yapmanız gerekiyor."):
    return error_response("unauthorized", message, 401)


def forbidden(message: str = "Bu işlem için yetkiniz yok."):
    return error_response("forbidden", message, 403)


def not_found(message: str):
    return error_response("not_found", message, 404)


def conflict(message: str, details: dict = None):
    return error_response("conflict", message, 409, details)


def validation_error(message: str, details: dict = None):
    return error_response("validation_error", message, 400, details)