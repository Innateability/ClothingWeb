from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, flash, jsonify)
from app.models import (Buyer, Product, ProductType, ProductKind,
                        CartItem, Order, OrderItem, Payment, Admin, Color)
from app import db
from app.utils import clean_expired_cart_items
from app.decorators import buyer_required
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from app.paystack import initialize_payment, verify_payment

base_bp = Blueprint("base", __name__)


def get_admin():
    return Admin.query.first()


def get_cart_count():
    if session.get("buyer_id"):
        return CartItem.query.filter_by(buyer_id=session["buyer_id"]).count()
    return 0


# ── SHOP / HOME ───────────────────────────────────────────────

@base_bp.route("/")
def index():
    admin  = get_admin()
    types  = ProductType.query.all()
    colors = Color.query.order_by(Color.name).all()

    type_id   = request.args.get("type_id",   type=int)
    kind_id   = request.args.get("kind_id",   type=int)
    gender    = request.args.get("gender")
    color_id  = request.args.get("color_id",  type=int)
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    size      = request.args.get("size")
    on_sale   = request.args.get("on_sale")

    query = Product.query.filter_by(is_active=True)

    if type_id:
        query = query.filter_by(product_type_id=type_id)
    if kind_id:
        query = query.filter_by(kind_id=kind_id)
    if gender:
        query = query.filter_by(gender=gender)
    if color_id:
        query = query.filter(Product.colors.any(Color.id == color_id))
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    if size:
        query = query.filter(Product.sizes.ilike(f"%{size}%"))
    if on_sale:
        query = query.filter_by(on_sale=True)

    products = query.order_by(Product.created_at.desc()).all()

    return render_template("index.html",
        products=products,
        types=types,
        colors=colors,
        admin=admin,
        cart_count=get_cart_count(),
        selected_type_id=type_id,
        selected_kind_id=kind_id,
        selected_gender=gender,
        selected_color_id=color_id,
        min_price=min_price,
        max_price=max_price,
        selected_size=size,
        on_sale=on_sale,
    )


@base_bp.route("/product/<int:product_id>")
def product_detail(product_id):
    product = db.get_or_404(Product, product_id)
    admin   = get_admin()
    return render_template("product_detail.html",
        product=product,
        admin=admin,
        cart_count=get_cart_count()
    )


@base_bp.route("/kinds/<int:type_id>")
def get_kinds(type_id):
    kinds = ProductKind.query.filter_by(product_type_id=type_id).all()
    return jsonify({"kinds": [{"id": k.id, "name": k.name} for k in kinds]})


# ── AUTH ──────────────────────────────────────────────────────

@base_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name     = request.form.get("name")
        email    = request.form.get("email")
        password = request.form.get("password")
        phone    = request.form.get("phone")

        if Buyer.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for("base.register"))

        buyer = Buyer(
            name=name,
            email=email,
            password=generate_password_hash(password),
            phone=phone
        )
        db.session.add(buyer)
        db.session.commit()

        session["buyer_id"]   = buyer.id
        session["buyer_name"] = buyer.name
        flash("Account created! Welcome.", "success")
        return redirect(url_for("base.index"))

    admin = get_admin()
    return render_template("register.html", admin=admin, cart_count=0)


@base_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email")
        password = request.form.get("password")
        buyer    = Buyer.query.filter_by(email=email).first()

        if not buyer or not check_password_hash(buyer.password, password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("base.login"))

        session["buyer_id"]   = buyer.id
        session["buyer_name"] = buyer.name
        flash("Welcome back!", "success")
        return redirect(request.args.get("next") or url_for("base.index"))

    admin = get_admin()
    return render_template("login.html", admin=admin, cart_count=0)


@base_bp.route("/logout")
def logout():
    session.pop("buyer_id",   None)
    session.pop("buyer_name", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("base.index"))


# ── CART ──────────────────────────────────────────────────────

@base_bp.route("/cart")
@buyer_required
def cart():
    buyer_id = session["buyer_id"]

    removed = clean_expired_cart_items(buyer_id)
    if removed:
        flash(f"{removed} expired item(s) removed from your cart.", "warning")

    items = CartItem.query.filter_by(buyer_id=buyer_id).all()
    admin = get_admin()
    return render_template("cart.html",
        items=items,
        admin=admin,
        cart_count=len(items)
    )


@base_bp.route("/cart/add/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    if not session.get("buyer_id"):
        flash("Please log in to add items to your cart.", "error")
        return redirect(url_for("base.login",
            next=url_for("base.product_detail", product_id=product_id)))

    product  = db.get_or_404(Product, product_id)
    buyer_id = session["buyer_id"]
    size     = request.form.get("size")
    quantity = int(request.form.get("quantity", 1))

    existing = CartItem.query.filter_by(
        buyer_id=buyer_id,
        product_id=product_id,
        size=size
    ).first()

    if existing:
        existing.quantity += quantity
    else:
        item = CartItem(
            buyer_id=buyer_id,
            product_id=product_id,
            quantity=quantity,
            size=size,
            price_at_add=product.effective_price(),
        )
        db.session.add(item)

    db.session.commit()
    flash(f'"{product.name}" added to cart.', "success")
    return redirect(request.referrer or url_for("base.index"))


@base_bp.route("/cart/remove/<int:item_id>", methods=["POST"])
@buyer_required
def remove_from_cart(item_id):
    item = db.get_or_404(CartItem, item_id)
    if item.buyer_id != session.get("buyer_id"):
        flash("Unauthorized.", "error")
        return redirect(url_for("base.cart"))
    db.session.delete(item)
    db.session.commit()
    flash("Item removed from cart.", "success")
    return redirect(url_for("base.cart"))


# ── CHECKOUT ──────────────────────────────────────────────────

@base_bp.route("/checkout", methods=["POST"])
@buyer_required
def checkout():
    buyer_id     = session["buyer_id"]
    selected_ids = request.form.getlist("selected_items")

    if not selected_ids:
        flash("Please select at least one item to checkout.", "error")
        return redirect(url_for("base.cart"))

    items = CartItem.query.filter(
        CartItem.id.in_(selected_ids),
        CartItem.buyer_id == buyer_id
    ).all()

    if not items:
        flash("No valid items selected.", "error")
        return redirect(url_for("base.cart"))

    admin = get_admin()
    if not admin:
        flash("Store not configured yet.", "error")
        return redirect(url_for("base.cart"))

    buyer = db.get_or_404(Buyer, buyer_id)

    total = sum(
        float(item.product.effective_price()) * item.quantity
        for item in items
    )

    # Create order in DB
    order = Order(
        buyer_id=buyer_id,
        total=total,
        status="pending",
        notes=request.form.get("notes")
    )
    db.session.add(order)
    db.session.flush()

    for item in items:
        oi = OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            size=item.size,
            price=item.product.effective_price(),
        )
        db.session.add(oi)
        db.session.delete(item)

    payment = Payment(
        order_id=order.id,
        admin_id=admin.id,
        amount=total,
    )
    db.session.add(payment)
    db.session.commit()

    # Initialize Paystack payment
    from app.paystack import initialize_payment

    callback_url = url_for("base.payment_callback", _external=True)

    auth_url, reference = initialize_payment(
        email=buyer.email,
        amount_naira=total,
        order_id=order.id,
        callback_url=callback_url,
        metadata={
            "order_id":    order.id,
            "buyer_name":  buyer.name,
            "buyer_email": buyer.email,
        }
    )

    if auth_url:
        session["paystack_ref"]     = reference
        session["pending_order_id"] = order.id
        return redirect(auth_url)
    else:
        # Paystack unreachable — show manual payment page
        flash("Online payment unavailable. Please pay manually.", "warning")
        return render_template("checkout_confirm.html",
            order=order,
            admin=admin,
            cart_count=0,
            manual=True,
            reference=None
        )


@base_bp.route("/payment/callback")
@buyer_required
def payment_callback():
    """
    Paystack redirects buyer here after payment.
    Verifies the transaction and updates order status.
    """
    from app.paystack import verify_payment
    from datetime import datetime

    reference = request.args.get("reference") or session.get("paystack_ref")
    order_id  = session.get("pending_order_id")

    if not reference or not order_id:
        flash("Invalid payment session.", "error")
        return redirect(url_for("base.orders"))

    order = db.session.get(Order, order_id)
    if not order:
        flash("Order not found.", "error")
        return redirect(url_for("base.orders"))

    success, data = verify_payment(reference)

    if success:
        order.status = "confirmed"

        if order.payment:
            order.payment.confirmed    = True
            order.payment.confirmed_at = datetime.utcnow()
            order.payment.buyer_note   = f"Paid via Paystack. Ref: {reference}"

        db.session.commit()

        session.pop("paystack_ref",     None)
        session.pop("pending_order_id", None)

        flash("Payment successful! Your order is confirmed. 🎉", "success")
        return render_template("checkout_confirm.html",
            order=order,
            admin=get_admin(),
            cart_count=0,
            manual=False,
            reference=reference
        )

    else:
        # Payment failed or cancelled
        order.status = "failed"
        db.session.commit()

        session.pop("paystack_ref",     None)
        session.pop("pending_order_id", None)

        flash("Payment was not completed. Please try again.", "error")
        return render_template("checkout_confirm.html",
            order=order,
            admin=get_admin(),
            cart_count=0,
            manual=True,
            reference=None
        )


@base_bp.route("/payment/retry/<int:order_id>")
@buyer_required
def retry_payment(order_id):
    """
    Lets buyer retry Paystack payment for a pending/failed order.
    """
    from app.paystack import initialize_payment

    order = db.get_or_404(Order, order_id)
    buyer = db.get_or_404(Buyer, session["buyer_id"])

    # Only allow retry if order belongs to this buyer
    if order.buyer_id != session["buyer_id"]:
        flash("Unauthorized.", "error")
        return redirect(url_for("base.orders"))

    # Only retry pending or failed orders
    if order.status == "confirmed":
        flash("This order has already been paid.", "success")
        return redirect(url_for("base.orders"))

    callback_url = url_for("base.payment_callback", _external=True)

    auth_url, reference = initialize_payment(
        email=buyer.email,
        amount_naira=order.total,
        order_id=order.id,
        callback_url=callback_url,
        metadata={
            "order_id":    order.id,
            "buyer_name":  buyer.name,
            "buyer_email": buyer.email,
            "retry":       True,
        }
    )

    if auth_url:
        session["paystack_ref"]     = reference
        session["pending_order_id"] = order.id
        return redirect(auth_url)
    else:
        flash("Could not connect to payment gateway. Please try later.", "error")
        return redirect(url_for("base.orders"))


@base_bp.route("/payment/webhook", methods=["POST"])
def paystack_webhook():
    """
    Paystack sends payment events here automatically.
    Use this to confirm payments server-side even if
    the buyer closes the browser before the callback.
    Set this URL in your Paystack dashboard → API → Webhooks
    """
    import hmac
    import hashlib
    import json
    from datetime import datetime

    secret = os.getenv("PAYSTACK_SECRET_KEY", "")

    # Verify the webhook signature
    signature = request.headers.get("X-Paystack-Signature", "")
    body      = request.get_data()
    expected  = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha512
    ).hexdigest()

    if signature != expected:
        return {"status": "unauthorized"}, 401

    event = json.loads(body)

    if event.get("event") == "charge.success":
        data      = event["data"]
        reference = data.get("reference", "")
        meta      = data.get("metadata", {})
        order_id  = meta.get("order_id")

        if order_id:
            order = db.session.get(Order, int(order_id))
            if order and order.status != "confirmed":
                order.status = "confirmed"
                if order.payment:
                    order.payment.confirmed    = True
                    order.payment.confirmed_at = datetime.utcnow()
                    order.payment.buyer_note   = f"Paystack webhook. Ref: {reference}"
                db.session.commit()

    return {"status": "ok"}, 200


# ── ORDERS ────────────────────────────────────────────────────

@base_bp.route("/orders")
@buyer_required
def orders():
    buyer_id   = session["buyer_id"]
    all_orders = Order.query.filter_by(buyer_id=buyer_id).order_by(
        Order.created_at.desc()
    ).all()
    admin = get_admin()
    return render_template("orders.html",
        orders=all_orders,
        admin=admin,
        cart_count=get_cart_count()
    )