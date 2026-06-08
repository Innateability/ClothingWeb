from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from app.models import Buyer, Order, CartItem, WishlistItem, Admin, StoreSettings
from app import db
from app.decorators import buyer_required

buyer_bp = Blueprint("buyer", __name__, url_prefix="/account")


def get_admin():
    return Admin.query.first()


def get_settings():
    return StoreSettings.query.first()


def get_cart_count():
    if session.get("buyer_id"):
        return CartItem.query.filter_by(buyer_id=session["buyer_id"]).count()
    return 0


def get_wishlist_count():
    if session.get("buyer_id"):
        return WishlistItem.query.filter_by(buyer_id=session["buyer_id"]).count()
    return 0


@buyer_bp.route("/profile")
@buyer_required
def profile():
    buyer  = db.get_or_404(Buyer, session["buyer_id"])
    orders = Order.query.filter_by(buyer_id=buyer.id).order_by(
        Order.created_at.desc()
    ).all()
    from datetime import datetime
    return render_template("profile.html",
        buyer=buyer,
        orders=orders,
        admin=get_admin(),
        settings=get_settings(),
        cart_count=get_cart_count(),
        wishlist_count=get_wishlist_count(),
        now=datetime.utcnow(),
    )


@buyer_bp.route("/update-address", methods=["POST"])
@buyer_required
def update_address():
    buyer = db.get_or_404(Buyer, session["buyer_id"])
    buyer.saved_address = request.form.get("address", "").strip()
    buyer.saved_city    = request.form.get("city",    "").strip()
    buyer.saved_state   = request.form.get("state",   "").strip()
    db.session.commit()
    flash("Address saved successfully.", "success")
    return redirect(url_for("buyer.profile"))