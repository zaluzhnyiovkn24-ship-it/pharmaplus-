from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.http import JsonResponse
from .models import Product, Category, Order, OrderItem

def product_list(request, category_id=None):
    """Каталог товарів з фільтрацією за категорією"""
    categories = Category.objects.all()
    selected_category = None
    
    cat_id = category_id or request.GET.get('category')
    
    if cat_id:
        selected_category = get_object_or_404(Category, pk=cat_id)
        products = Product.objects.filter(category=selected_category)
    else:
        products = Product.objects.all()
        
    return render(request, 'pharmacy/product_list.html', {
        'products': products,
        'categories': categories,
        'selected_category': selected_category
    })

def category_detail(request, category_id):
    """Аліас для перегляду категорії"""
    return product_list(request, category_id=category_id)

def product_detail(request, pk):
    """Сторінка деталей товару"""
    product = get_object_or_404(Product, pk=pk)
    return render(request, 'pharmacy/product_detail.html', {'product': product})

def search_suggest(request):
    """Автопідказки для пошуку"""
    query = request.GET.get('q', '')
    if query:
        products = Product.objects.filter(name__icontains=query)[:5]
        results = [{'id': p.id, 'name': p.name, 'price': str(p.price)} for p in products]
    else:
        results = []
    return JsonResponse(results, safe=False)

def register_view(request):
    """Реєстрація користувача"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Акаунт успішно створено! Увійдіть.')
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'pharmacy/register.html', {'form': form})

def login_view(request):
    """Авторизація користувача"""
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            return redirect('product_list')
    else:
        form = AuthenticationForm()
    return render(request, 'pharmacy/login.html', {'form': form})

def logout_view(request):
    """Вихід із системи"""
    auth_logout(request)
    messages.info(request, 'Ви успішно вийшли з акаунту.')
    return redirect('product_list')

# --- ЛОГІКА КОШИКА ---

@login_required
def cart_detail(request):
    """Перегляд кошика з підрахунком суми"""
    cart = request.session.get('cart', {})
    cart_items = []
    total_price = 0
    
    for product_id, quantity in cart.items():
        product = Product.objects.filter(id=product_id).first()
        if product:
            item_total = product.price * quantity
            total_price += item_total
            cart_items.append({
                'product': product,
                'quantity': quantity,
                'total_price': item_total
            })
            
    return render(request, 'pharmacy/cart_detail.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })

@login_required
def cart_add(request, product_id):
    """Додавання товару в кошик"""
    cart = request.session.get('cart', {})
    str_id = str(product_id)
    cart[str_id] = cart.get(str_id, 0) + 1
    request.session['cart'] = cart
    messages.success(request, 'Товар додано в кошик!')
    return redirect(request.META.get('HTTP_REFERER', 'product_list'))

@login_required
def cart_decrement(request, product_id):
    """Зменшення кількості товару в кошику"""
    cart = request.session.get('cart', {})
    str_id = str(product_id)
    if str_id in cart:
        cart[str_id] -= 1
        if cart[str_id] <= 0:
            del cart[str_id]
        request.session['cart'] = cart
    return redirect('cart_detail')

@login_required
def cart_remove(request, product_id):
    """Видалення товару з кошика"""
    cart = request.session.get('cart', {})
    str_id = str(product_id)
    if str_id in cart:
        del cart[str_id]
        request.session['cart'] = cart
        messages.success(request, 'Товар видалено з кошика.')
    return redirect('cart_detail')

@login_required
def add_to_cart(request, pk):
    return cart_add(request, pk)

@login_required
def remove_from_cart(request, pk):
    return cart_remove(request, pk)

# --- ОФОРМЛЕННЯ ЗАМОВЛЕННЯ З ОПЛАТОЮ КАРТКОЮ ---
@login_required
def checkout(request):
    """Оформлення замовлення з перевіркою картки, рецепта та збереженням товарів"""
    cart = request.session.get('cart', {})

    if not cart:
        messages.warning(request, 'Ваш кошик порожній!')
        return redirect('cart_detail')

    # Перевіряємо, чи є в кошику хоча б один рецептурний препарат
    has_prescription = Product.objects.filter(id__in=cart.keys(), is_prescription=True).exists()

    if request.method == 'POST':
        # Отримуємо спосіб оплати з форми (за замовчуванням 'cash')
        payment_method = request.POST.get('payment_method', 'cash')

        # Перевірка картки ТІЛЬКИ якщо вибрано оплату карткою
        if payment_method == 'card':
            card_number = request.POST.get('card_number', '').replace(' ', '')
            if not card_number or len(card_number) < 16 or not card_number.isdigit():
                messages.error(request, 'Будь ласка, введіть коректний 16-значний номер картки!')
                return render(request, 'pharmacy/checkout.html', {'has_prescription': has_prescription})

        # Отримуємо телефон, адресу та номер рецепта з форми
        phone = request.POST.get('phone', '')
        address = request.POST.get('address', '')
        prescription_number = request.POST.get('prescription_number', '').strip()

        # Блокуємо замовлення, якщо потрібен рецепт, а поле порожнє
        if has_prescription and not prescription_number:
            messages.error(request, 'Для рецептурних препаратів необхідно вказати номер електронного рецепта!')
            return render(request, 'pharmacy/checkout.html', {'has_prescription': has_prescription})

        # Рахуємо загальну суму кошика
        total_price = 0
        for product_id, quantity in cart.items():
            try:
                product = Product.objects.get(id=product_id)
                total_price += product.price * quantity
            except Product.DoesNotExist:
                continue

        # Створюємо ГОЛОВНЕ замовлення
        order = Order.objects.create(
            user=request.user,
            payment_method=payment_method,
            phone=phone,
            address=address,
            prescription_number=prescription_number if has_prescription else None,
            total_price=total_price,
            status='pending'
        )

        # Додаємо ТОВАРИ до цього замовлення (щоб вони з'явилися в адмінці)
        for product_id, quantity in cart.items():
            try:
                product = Product.objects.get(id=product_id)
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    price=product.price
                )
            except Product.DoesNotExist:
                continue

        # Очищення кошика після успішного оформлення
        request.session['cart'] = {}
        request.session.modified = True

        messages.success(request, 'Замовлення успішно оформлено!')
        return redirect('profile')

    return render(request, 'pharmacy/checkout.html', {'has_prescription': has_prescription})
@login_required
def process_payment(request, order_id):
    """Оплата замовлення"""
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    messages.success(request, f'Оплата замовлення №{order.id} пройшла успішно!')
    return redirect('profile')

@login_required
def delete_order(request, order_id):
    """Видалення замовлення"""
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    order.delete()
    messages.success(request, 'Замовлення видалено!')
    return redirect('profile')

@login_required
def profile_view(request):
    """Профіль користувача"""
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'pharmacy/profile.html', {
        'orders': orders,
        'user': request.user
    })

@login_required
def clear_order_history(request):
    """Очищення історії замовлень"""
    if request.method == 'POST':
        Order.objects.filter(user=request.user).delete()
    return redirect('profile')