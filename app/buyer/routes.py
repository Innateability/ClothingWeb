from flask import Blueprint, render_template, session, redirect, url_for, flash
from app.models import Buyer, Order, CartItem, Admin
from app import db
from app.decorators import buyer_required

buyer_bp = Blueprint("buyer", __name__, url_prefix="/account")


def get_admin():
    return Admin.query.first()


@buyer_bp.route("/profile")
@buyer_required
def profile():
    buyer  = db.get_or_404(Buyer, session["buyer_id"])
    orders = Order.query.filter_by(buyer_id=buyer.id).order_by(
        Order.created_at.desc()
    ).all()
    admin      = get_admin()
    cart_count = CartItem.query.filter_by(buyer_id=buyer.id).count()

    return render_template("profile.html",
        buyer=buyer,
        orders=orders,
        admin=admin,
        cart_count=cart_count
    )