from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from .models import Order, OrderItem, Product


@transaction.atomic
def place_order(user, cart, token, phone, address, method, prescription):
    previous = Order.objects.filter(user=user, checkout_token=token).first()
    if previous:
        return previous

    products = Product.objects.in_bulk(cart)
    lines = []
    total = Decimal("0.00")
    for identifier, quantity in cart.items():
        product = products.get(int(identifier))
        if not product or not isinstance(quantity, int) or quantity < 1:
            raise ValidationError("Позиція кошика змінилася. Оновіть кошик.")
        if product.is_prescription and not prescription:
            raise ValidationError("Для цього товару потрібен номер рецепта.")
        updated = Product.objects.filter(pk=product.pk, stock__gte=quantity).update(
            stock=F("stock") - quantity
        )
        if not updated:
            raise ValidationError(f"Недостатній залишок товару «{product.name}».")
        total += product.price * quantity
        lines.append(OrderItem(product=product, price=product.price, quantity=quantity))

    order = Order.objects.create(
        user=user, checkout_token=token, phone=phone, address=address,
        payment_method=method, total_price=total,
        prescription_number=prescription if any(p.is_prescription for p in products.values()) else None,
    )
    for line in lines:
        line.order = order
    OrderItem.objects.bulk_create(lines)
    return order
