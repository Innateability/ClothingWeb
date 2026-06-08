from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, flash, jsonify)
from app.models import (Buyer, Product, ProductType, ProductKind,
                        CartItem, Order, OrderItem, Payment, Admin,
                        Color, WishlistItem, WaitlistItem, StoreSettings)
from app import db
from app.utils import clean_expired_cart_items
from app.decorators import buyer_required
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

base_bp = Blueprint("base", __name__)


# ── HELPERS ───────────────────────────────────────────────────

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


def delivery_date_str(settings):
    days = settings.delivery_days if settings and settings.delivery_days else 3
    return (datetime.utcnow() + timedelta(days=days)).strftime('%A, %d %B %Y')


def base_ctx():
    return dict(
        admin=get_admin(),
        settings=get_settings(),
        cart_count=get_cart_count(),
        wishlist_count=get_wishlist_count(),
        now=datetime.utcnow(),
    )


# ── SHOP ──────────────────────────────────────────────────────

@base_bp.route("/")
def index():
    ctx    = base_ctx()
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
        selected_type_id=type_id,
        selected_kind_id=kind_id,
        selected_gender=gender,
        selected_color_id=color_id,
        min_price=min_price,
        max_price=max_price,
        selected_size=size,
        on_sale=on_sale,
        **ctx
    )


@base_bp.route("/product/<int:product_id>")
def product_detail(product_id):
    product = db.get_or_404(Product, product_id)
    related = product.related_products(limit=4)
    ctx     = base_ctx()

    # ✅ FIXED: just CHECK if in wishlist — do NOT delete it
    in_wishlist = False
    if session.get("buyer_id"):
        in_wishlist = WishlistItem.query.filter_by(
            buyer_id=session["buyer_id"],
            product_id=product_id
        ).first() is not None

    return render_template("product_detail.html",
        product=product,
        related=related,
        in_wishlist=in_wishlist,
        **ctx
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
            name=name, email=email,
            password=generate_password_hash(password), phone=phone
        )
        db.session.add(buyer)
        db.session.commit()

        session["buyer_id"]   = buyer.id
        session["buyer_name"] = buyer.name
        flash("Account created! Welcome.", "success")
        return redirect(url_for("base.index"))

    return render_template("register.html", **base_ctx())


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

    return render_template("login.html", **base_ctx())


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
    removed  = clean_expired_cart_items(buyer_id)
    if removed:
        flash(f"{removed} expired item(s) removed.", "warning")

    items    = CartItem.query.filter_by(buyer_id=buyer_id).all()
    settings = get_settings()
    ctx      = base_ctx()
    return render_template("cart.html",
        items=items,
        delivery_date=delivery_date_str(settings),
        **ctx
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
    color    = request.form.get("color")
    quantity = int(request.form.get("quantity", 1))

    if product.stock < 1:
        flash(f'"{product.name}" is out of stock.', "error")
        return redirect(url_for("base.product_detail", product_id=product_id))

    existing = CartItem.query.filter_by(
        buyer_id=buyer_id, product_id=product_id, size=size
    ).first()

    already_in_cart = existing.quantity if existing else 0
    if already_in_cart + quantity > product.stock:
        quantity = product.stock - already_in_cart
        if quantity <= 0:
            flash(f'Max stock already in cart.', "warning")
            return redirect(url_for("base.cart"))
        flash(f'Only {quantity} more available. Cart updated.', "warning")

    if existing:
        existing.quantity += quantity
    else:
        db.session.add(CartItem(
            buyer_id=buyer_id, product_id=product_id,
            quantity=quantity, size=size, color=color,
            price_at_add=product.effective_price(),
        ))

    db.session.commit()
    flash(f'"{product.name}" added to cart.', "success")
    # ✅ Always redirect to cart after adding
    return redirect(url_for("base.cart"))


@base_bp.route("/cart/remove/<int:item_id>", methods=["POST"])
@buyer_required
def remove_from_cart(item_id):
    item = db.get_or_404(CartItem, item_id)
    if item.buyer_id != session["buyer_id"]:
        flash("Unauthorized.", "error")
        return redirect(url_for("base.cart"))
    db.session.delete(item)
    db.session.commit()
    flash("Item removed.", "success")
    return redirect(url_for("base.cart"))


@base_bp.route("/cart/move-to-wishlist/<int:item_id>", methods=["POST"])
@buyer_required
def move_to_wishlist(item_id):
    item = db.get_or_404(CartItem, item_id)
    if item.buyer_id != session["buyer_id"]:
        flash("Unauthorized.", "error")
        return redirect(url_for("base.cart"))

    existing = WishlistItem.query.filter_by(
        buyer_id=session["buyer_id"], product_id=item.product_id
    ).first()

    if not existing:
        db.session.add(WishlistItem(
            buyer_id=session["buyer_id"], product_id=item.product_id
        ))

    db.session.delete(item)
    db.session.commit()
    flash("Moved to wishlist.", "success")
    return redirect(url_for("base.cart"))


# ── WISHLIST ──────────────────────────────────────────────────

@base_bp.route("/wishlist")
@buyer_required
def wishlist():
    buyer_id = session["buyer_id"]
    items    = WishlistItem.query.filter_by(buyer_id=buyer_id).order_by(
        WishlistItem.added_at.desc()
    ).all()
    return render_template("wishlist.html", items=items, **base_ctx())


@base_bp.route("/wishlist/add/<int:product_id>", methods=["POST", "GET"])
@buyer_required
def add_to_wishlist(product_id):
    buyer_id = session["buyer_id"]
    is_ajax  = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    existing = WishlistItem.query.filter_by(
        buyer_id=buyer_id, product_id=product_id
    ).first()

    if existing:
        # Toggle off — remove from wishlist
        db.session.delete(existing)
        db.session.commit()
        if is_ajax:
            return jsonify({"status": "removed", "message": "Removed from wishlist"})
        flash("Removed from wishlist.", "success")
    else:
        # Add to wishlist
        db.session.add(WishlistItem(buyer_id=buyer_id, product_id=product_id))
        db.session.commit()
        if is_ajax:
            return jsonify({"status": "added", "message": "Added to wishlist ♡"})
        flash("Added to wishlist ♡", "success")

    return redirect(request.referrer or url_for("base.index"))


@base_bp.route("/wishlist/remove/<int:item_id>", methods=["POST"])
@buyer_required
def remove_from_wishlist(item_id):
    item = db.get_or_404(WishlistItem, item_id)
    if item.buyer_id != session["buyer_id"]:
        flash("Unauthorized.", "error")
        return redirect(url_for("base.wishlist"))
    db.session.delete(item)
    db.session.commit()
    flash("Removed from wishlist.", "success")
    return redirect(url_for("base.wishlist"))


@base_bp.route("/wishlist/move-to-cart/<int:item_id>", methods=["POST"])
@buyer_required
def move_to_cart(item_id):
    item    = db.get_or_404(WishlistItem, item_id)
    product = item.product

    if item.buyer_id != session["buyer_id"]:
        flash("Unauthorized.", "error")
        return redirect(url_for("base.wishlist"))

    if product.stock < 1:
        flash(f'"{product.name}" is out of stock.', "error")
        return redirect(url_for("base.wishlist"))

    # If product has multiple sizes OR colors send to product page to choose
    has_sizes  = len(product.get_sizes()) > 1
    has_colors = len(product.colors) > 1

    if has_sizes or has_colors:
        flash(
            f'Please select your size/color for "{product.name}" before adding to cart.',
            "warning"
        )
        return redirect(url_for("base.product_detail", product_id=product.id))

    # No choices needed — add directly
    buyer_id = session["buyer_id"]
    size     = product.get_sizes()[0] if product.get_sizes() else None
    color    = product.colors[0].name if product.colors else None

    existing = CartItem.query.filter_by(
        buyer_id=buyer_id, product_id=product.id, size=size
    ).first()

    if existing:
        if existing.quantity < product.stock:
            existing.quantity += 1
        else:
            flash(f'Max stock already in cart for "{product.name}".', "warning")
            return redirect(url_for("base.wishlist"))
    else:
        db.session.add(CartItem(
            buyer_id=buyer_id,
            product_id=product.id,
            quantity=1,
            size=size,
            color=color,
            price_at_add=product.effective_price()
        ))

    db.session.delete(item)
    db.session.commit()
    flash(f'"{product.name}" moved to cart.', "success")
    return redirect(url_for("base.wishlist"))


# ── WAITLIST ──────────────────────────────────────────────────

@base_bp.route("/waitlist/join/<int:product_id>", methods=["POST"])
@buyer_required
def join_waitlist(product_id):
    buyer_id = session["buyer_id"]
    existing = WaitlistItem.query.filter_by(
        buyer_id=buyer_id, product_id=product_id
    ).first()

    if existing:
        flash("You're already on the waitlist for this item.", "warning")
        return redirect(request.referrer or url_for("base.index"))

    db.session.add(WaitlistItem(
        buyer_id=buyer_id,
        product_id=product_id,
        size=request.form.get("size"),
        color=request.form.get("color"),
        note=request.form.get("note"),
    ))
    db.session.commit()
    flash("You're on the waitlist! We'll notify you when it's back in stock.", "success")
    return redirect(request.referrer or url_for("base.index"))


# ── CHECKOUT ──────────────────────────────────────────────────

@base_bp.route("/checkout", methods=["POST"])
@buyer_required
def checkout():
    buyer_id     = session["buyer_id"]
    selected_ids = request.form.getlist("selected_items")

    if not selected_ids:
        flash("Please select at least one item.", "error")
        return redirect(url_for("base.cart"))

    items = CartItem.query.filter(
        CartItem.id.in_(selected_ids),
        CartItem.buyer_id == buyer_id
    ).all()

    if not items:
        flash("No valid items selected.", "error")
        return redirect(url_for("base.cart"))

    settings = get_settings()
    total    = sum(float(i.product.effective_price()) * i.quantity for i in items)

    session["checkout_ids"]   = [i.id for i in items]
    session["checkout_total"] = float(total)
    session["checkout_notes"] = request.form.get("notes", "")

    buyer = db.get_or_404(Buyer, buyer_id)
    return render_template("checkout_address.html",
        items=items,
        total=total,
        selected_ids=selected_ids,
        notes=request.form.get("notes", ""),
        buyer=buyer,
        delivery_date=delivery_date_str(settings),
        **base_ctx()
    )


@base_bp.route("/checkout/confirm-address", methods=["POST"])
@buyer_required
def checkout_confirm_address():
    buyer_id = session["buyer_id"]
    buyer    = db.get_or_404(Buyer, buyer_id)
    admin    = get_admin()
    settings = get_settings()

    selected_ids     = request.form.getlist("selected_items")
    delivery_address = request.form.get("delivery_address", "").strip()
    delivery_city    = request.form.get("delivery_city", "").strip()
    delivery_state   = request.form.get("delivery_state", "").strip()
    notes            = request.form.get("notes", "")
    save_address     = request.form.get("save_address") == "1"

    if not delivery_address or not delivery_city:
        flash("Please enter a delivery address.", "error")
        return redirect(url_for("base.checkout"))

    if save_address:
        buyer.saved_address = delivery_address
        buyer.saved_city    = delivery_city
        buyer.saved_state   = delivery_state
        db.session.commit()

    items = CartItem.query.filter(
        CartItem.id.in_(selected_ids),
        CartItem.buyer_id == buyer_id
    ).all()

    total = sum(float(i.product.effective_price()) * i.quantity for i in items)

    delivery_days      = settings.delivery_days if settings and settings.delivery_days else 3
    estimated_delivery = datetime.utcnow() + timedelta(days=delivery_days)

    order = Order(
        buyer_id=buyer_id,
        total=total,
        status="pending",
        notes=notes,
        delivery_address=delivery_address,
        delivery_city=delivery_city,
        delivery_state=delivery_state,
        estimated_delivery=None,  # set only after payment confirmed
    )
    db.session.add(order)
    db.session.flush()

    for item in items:
        db.session.add(OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            size=item.size,
            color=item.color,
            price=item.product.effective_price(),
        ))
        item.product.stock = max(0, item.product.stock - item.quantity)
        db.session.delete(item)

    db.session.add(Payment(
        order_id=order.id,
        admin_id=admin.id,
        amount=total,
    ))
    db.session.commit()

    try:
        from app.paystack import initialize_payment
        callback_url = url_for("base.payment_callback", _external=True)
        auth_url, reference = initialize_payment(
            email=buyer.email,
            amount_naira=total,
            order_id=order.id,
            callback_url=callback_url,
        )
        if auth_url:
            session["paystack_ref"]     = reference
            session["pending_order_id"] = order.id
            return redirect(auth_url)
    except Exception:
        pass

    flash("Pay via bank transfer to complete your order.", "warning")
    return render_template("checkout_confirm.html",
        order=order, manual=True, reference=None, **base_ctx()
    )


# ── PAYMENT CALLBACK ──────────────────────────────────────────

@base_bp.route("/payment/callback")
@buyer_required
def payment_callback():
    from app.paystack import verify_payment

    reference = request.args.get("reference") or session.get("paystack_ref")
    order_id  = session.get("pending_order_id")

    if not reference or not order_id:
        flash("Invalid payment session.", "error")
        return redirect(url_for("base.orders"))

    order         = db.session.get(Order, order_id)
    success, data = verify_payment(reference)

    if success:
        order.status = "confirmed"
        if order.payment:
            order.payment.confirmed    = True
            order.payment.confirmed_at = datetime.utcnow()
            order.payment.buyer_note   = f"Paystack Ref: {reference}"

        # ✅ Calculate delivery from time of payment confirmation
        settings = get_settings()
        delivery_days = settings.delivery_days if settings and settings.delivery_days else 3
        order.estimated_delivery = datetime.utcnow() + timedelta(days=delivery_days)

        db.session.commit()
        session.pop("paystack_ref",     None)
        session.pop("pending_order_id", None)
        flash("Payment confirmed! 🎉", "success")
        return render_template("checkout_confirm.html",
            order=order, manual=False, reference=reference, **base_ctx()
        )
    else:
        order.status = "failed"
        db.session.commit()
        flash("Payment failed. Please try again.", "error")
        return render_template("checkout_confirm.html",
            order=order, manual=True, reference=None, **base_ctx()
        )


@base_bp.route("/payment/retry/<int:order_id>")
@buyer_required
def retry_payment(order_id):
    from app.paystack import initialize_payment
    order = db.get_or_404(Order, order_id)
    buyer = db.get_or_404(Buyer, session["buyer_id"])

    if order.buyer_id != session["buyer_id"]:
        flash("Unauthorized.", "error")
        return redirect(url_for("base.orders"))

    if order.status == "confirmed":
        flash("Already paid.", "success")
        return redirect(url_for("base.orders"))

    try:
        callback_url = url_for("base.payment_callback", _external=True)
        auth_url, reference = initialize_payment(
            email=buyer.email,
            amount_naira=order.total,
            order_id=order.id,
            callback_url=callback_url,
        )
        if auth_url:
            session["paystack_ref"]     = reference
            session["pending_order_id"] = order.id
            return redirect(auth_url)
    except Exception:
        pass

    flash("Could not connect to payment. Please pay via bank transfer.", "warning")
    return render_template("checkout_confirm.html",
        order=order, manual=True, reference=None, **base_ctx()
    )


# ── ORDERS ────────────────────────────────────────────────────

@base_bp.route("/orders")
@buyer_required
def orders():
    buyer_id   = session["buyer_id"]
    all_orders = Order.query.filter_by(buyer_id=buyer_id).order_by(
        Order.created_at.desc()
    ).all()
    return render_template("orders.html", orders=all_orders, **base_ctx())


# ── LEGAL PAGES ───────────────────────────────────────────────

@base_bp.route("/terms")
def terms():
    return render_template("terms.html", **base_ctx())


@base_bp.route("/privacy")
def privacy():
    return render_template("privacy.html", **base_ctx())


@base_bp.route("/refund")
def refund():
    return render_template("refund.html", **base_ctx())