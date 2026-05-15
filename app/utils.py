import os
import uuid
from datetime import datetime

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file, upload_folder):
    """
    Saves an uploaded image to the upload folder.
    Returns the saved filename or None if invalid.
    """
    if not file or file.filename == "":
        return None
    if not allowed_file(file.filename):
        return None

    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(upload_folder, exist_ok=True)
    file.save(os.path.join(upload_folder, filename))
    return filename


def clean_expired_cart_items(buyer_id):
    """
    Deletes all expired cart items for a given buyer.
    Returns the number of items removed.
    """
    from app.models import CartItem
    from app import db

    expired = CartItem.query.filter(
        CartItem.buyer_id == buyer_id,
        CartItem.expires_at < datetime.utcnow()
    ).all()

    if expired:
        for item in expired:
            db.session.delete(item)
        db.session.commit()

    return len(expired)