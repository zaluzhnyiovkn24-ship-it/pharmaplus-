from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import Category, Order, Product


class PharmacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model()
        cls.buyer = user.objects.create_user("buyer")
        cls.other = user.objects.create_user("other")
        cls.category = Category.objects.create(name="Вироби")
        other_category = Category.objects.create(name="Демо RX")
        cls.band = Product.objects.create(
            category=cls.category, name="Бинт", price="12.35", stock=3)
        cls.pad = Product.objects.create(
            category=cls.category, name="Серветка", price="4.20", stock=2)
        cls.rx = Product.objects.create(
            category=other_category, name="Зразок RX", price="21.00",
            stock=2, is_prescription=True)

    def setUp(self):
        self.client.force_login(self.buyer)

    def add(self, product):
        return self.client.post(reverse("cart_add", args=[product.pk]))

    def checkout_data(self, **changes):
        page = self.client.get(reverse("checkout"))
        return dict(phone="+380000000000", address="Тестова адреса",
                    checkout_token=page.context["checkout_token"],
                    payment_method="cash") | changes

    def test_01_catalog_filter(self):
        self.client.logout()
        page = self.client.get("/", {"category": self.category.pk, "q": "Бинт"})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, self.band.name)
        self.assertNotContains(page, self.pad.name)

    def test_02_search_suggestions(self):
        res = self.client.get(reverse("search_suggest"), {"q": "Бин"})
        self.assertEqual(res.json(), [
            {"id": self.band.pk, "name": "Бинт", "price": "12.35"}])

    def test_03_guest_cart(self):
        self.client.logout()
        res = self.client.get(reverse("cart_detail"))
        self.assertRedirects(res, reverse("login") + "?next=/cart/")

    def test_04_cart_quantities(self):
        self.add(self.band)
        self.add(self.band)
        self.client.post(reverse("cart_decrement", args=[self.band.pk]))
        self.assertEqual(self.client.session["cart"], {str(self.band.pk): 1})
        self.client.post(reverse("cart_remove", args=[self.band.pk]))
        self.assertEqual(self.client.session["cart"], {})

    def test_05_cart_stock_limit(self):
        for _ in range(4):
            self.add(self.band)
        self.assertEqual(self.client.session["cart"][str(self.band.pk)], 3)

    def test_06_order_total(self):
        self.add(self.band)
        self.add(self.band)
        self.add(self.pad)
        res = self.client.post(reverse("checkout"), self.checkout_data())
        self.assertRedirects(res, reverse("profile"))
        order = Order.objects.get(user=self.buyer)
        self.assertEqual(order.total_price, Decimal("28.90"))
        self.assertEqual(order.items.count(), 2)
        self.band.refresh_from_db()
        self.assertEqual(self.band.stock, 1)
        self.assertEqual(self.client.session["cart"], {})

    def test_07_prescription(self):
        self.add(self.rx)
        data = self.checkout_data()
        res = self.client.post(reverse("checkout"), data)
        self.assertContains(res, "потрібен номер рецепта")
        self.assertFalse(Order.objects.exists())
        data["prescription_number"] = "DEMO-001"
        self.client.post(reverse("checkout"), data)
        self.assertEqual(Order.objects.get().prescription_number, "DEMO-001")

    def test_08_stock_rollback(self):
        self.add(self.band)
        self.add(self.pad)
        data = self.checkout_data()
        Product.objects.filter(pk=self.pad.pk).update(stock=0)
        res = self.client.post(reverse("checkout"), data)
        self.assertContains(res, "Недостатній залишок")
        self.band.refresh_from_db()
        self.assertEqual(self.band.stock, 3)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(len(self.client.session["cart"]), 2)

    def test_09_order_ownership(self):
        foreign = Order.objects.create(user=self.other, payment_method="card")
        mine = Order.objects.create(user=self.buyer)
        page = self.client.get(reverse("profile"))
        self.assertEqual(list(page.context["orders"]), [mine])
        for route in ("delete_order", "process_payment"):
            res = self.client.post(reverse(route, args=[foreign.pk]))
            self.assertEqual(res.status_code, 404)
        self.client.post(reverse("clear_order_history"))
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, "pending")
        self.assertFalse(Order.objects.filter(pk=mine.pk).exists())

    def test_10_methods(self):
        order = Order.objects.create(user=self.buyer)
        for route, args in (("cart_add", [self.band.pk]),
                            ("cart_decrement", [self.band.pk]),
                            ("cart_remove", [self.band.pk]),
                            ("process_payment", [order.pk]),
                            ("delete_order", [order.pk]),
                            ("clear_order_history", []), ("logout", [])):
            url = reverse(route, args=args)
            self.assertEqual(self.client.get(url).status_code, 405)
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())

    def test_11_csrf_forms(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.buyer)
        page = browser.get("/")
        url = reverse("cart_add", args=[self.band.pk])
        self.assertEqual(browser.post(url).status_code, 403)
        token = str(page.context["csrf_token"])
        self.assertEqual(browser.post(url, {"csrfmiddlewaretoken": token}).status_code, 302)

    def test_12_demo_payment(self):
        card = Order.objects.create(user=self.buyer, payment_method="card")
        cash = Order.objects.create(user=self.buyer, payment_method="cash")
        for order in (card, card, cash):
            self.client.post(reverse("process_payment", args=[order.pk]))
        card.refresh_from_db()
        cash.refresh_from_db()
        self.assertEqual((card.status, cash.status), ("paid", "pending"))

    def test_13_repeat_checkout(self):
        self.add(self.band)
        data = self.checkout_data()
        original = dict(self.client.session)
        self.client.post(reverse("checkout"), data)
        session = self.client.session
        session.update(original)
        session.save()
        self.client.post(reverse("checkout"), data)
        self.assertEqual(Order.objects.count(), 1)
        self.band.refresh_from_db()
        self.assertEqual(self.band.stock, 2)

    def test_14_delivery_fields(self):
        self.add(self.band)
        data = self.checkout_data(phone="")
        res = self.client.post(reverse("checkout"), data)
        self.assertContains(res, "Перевірте контактний телефон")
        self.assertFalse(Order.objects.exists())
