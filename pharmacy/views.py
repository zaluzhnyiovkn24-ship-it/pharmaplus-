from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.http import Http404, JsonResponse
from .models import Product, Category, Order
from .orders import place_order

@require_GET
def product_list(request, category_id=None):
    """Каталог товарів з фільтрацією за категорією"""
    categories = Category.objects.all()
    selected_category = None
    
    cat_id = category_id or request.GET.get('category')
    
    if cat_id:
        if not str(cat_id).isascii() or not str(cat_id).isdigit() or len(str(cat_id)) > 18:
            raise Http404
        selected_category = get_object_or_404(Category, pk=cat_id)
        products = Product.objects.filter(category=selected_category)
    else:
        products = Product.objects.all()
        
    query = request.GET.get('q', '').strip()
    if query:
        products = products.filter(name__icontains=query)
    page = Paginator(products.order_by('name', 'pk'), 9).get_page(request.GET.get('page'))
    return render(request, 'pharmacy/product_list.html', {
        'products': page.object_list, 'page_obj': page, 'query': query,
        'categories': categories,
        'selected_category': selected_category
    })

def category_detail(request, category_id):
    """Аліас для перегляду категорії"""
    return product_list(request, category_id=category_id)

@require_GET
def product_detail(request, pk):
    """Сторінка деталей товару"""
    product = get_object_or_404(Product, pk=pk)
    return render(request, 'pharmacy/product_detail.html', {'product': product})

@require_GET
def search_suggest(request):
    """Автопідказки для пошуку"""
    query = request.GET.get('q', '').strip()
    if query:
        products = Product.objects.filter(name__icontains=query).order_by('name', 'pk')[:5]
        results = [{'id': p.id, 'name': p.name, 'price': str(p.price)} for p in products]
    else:
        results = []
    return JsonResponse(results, safe=False)

@require_http_methods(["GET", "POST"])
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

@require_http_methods(["GET", "POST"])
def login_view(request):
    """Авторизація користувача"""
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            target = request.GET.get('next', '')
            if url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
                return redirect(target)
            return redirect('product_list')
    else:
        form = AuthenticationForm()
    return render(request, 'pharmacy/login.html', {'form': form})

@require_POST
def logout_view(request):
    """Вихід із системи"""
    auth_logout(request)
    messages.info(request, 'Ви успішно вийшли з акаунту.')
    return redirect('product_list')

# --- ЛОГІКА КОШИКА ---

@login_required
@require_GET
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
@require_POST
def cart_add(request, product_id):
    """Додавання товару в кошик"""
    cart = request.session.get('cart', {})
    product = get_object_or_404(Product, pk=product_id)
    key = str(product.pk)
    if cart.get(key, 0) >= product.stock:
        messages.warning(request, 'Доступний залишок вичерпано.')
    else:
        cart[key] = cart.get(key, 0) + 1
        request.session['cart'] = cart
        request.session.pop('checkout_token', None)
        messages.success(request, 'Товар додано в кошик!')
    target = request.POST.get('next') or request.META.get('HTTP_REFERER', '')
    if url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        return redirect(target)
    return redirect('product_list')


@login_required
@require_POST
def cart_decrement(request, product_id):
    """Зменшення кількості товару в кошику"""
    cart = request.session.get('cart', {})
    str_id = str(product_id)
    if str_id in cart:
        cart[str_id] -= 1
        if cart[str_id] <= 0:
            del cart[str_id]
        request.session['cart'] = cart
        request.session.pop('checkout_token', None)
    return redirect('cart_detail')

@login_required
@require_POST
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

@login_required
@require_http_methods(["GET", "POST"])
def checkout(request):
    cart = request.session.get('cart', {})
    if not cart:
        return redirect('cart_detail')
    token = request.session.get('checkout_token')
    if not token:
        token = str(uuid4())
        request.session['checkout_token'] = token
    context = {
        'has_prescription': Product.objects.filter(pk__in=cart, is_prescription=True).exists(),
        'checkout_token': token,
        'values': request.POST,
    }
    if request.method == 'GET':
        return render(request, 'pharmacy/checkout.html', context)

    phone = request.POST.get('phone', '').strip()
    address = request.POST.get('address', '').strip()
    method = request.POST.get('payment_method', '')
    prescription = request.POST.get('prescription_number', '').strip()
    try:
        if request.POST.get('checkout_token') != token:
            raise ValidationError('Вміст кошика змінився. Перегляньте його та підтвердьте форму ще раз.')
        if not phone or len(phone) > 20 or not address or len(address) > 500:
            raise ValidationError('Перевірте контактний телефон та адресу доставки.')
        if method not in dict(Order.PAYMENT_METHOD_CHOICES) or len(prescription) > 50:
            raise ValidationError('Перевірте спосіб оплати та дані рецепта.')
        place_order(request.user, cart, token, phone, address, method, prescription)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return render(request, 'pharmacy/checkout.html', context)
    request.session['cart'] = {}
    request.session.pop('checkout_token', None)
    messages.success(request, 'Замовлення успішно оформлено!')
    return redirect('profile')


@login_required
@require_POST
def process_payment(request, order_id):
    """Оплата замовлення"""
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    if order.payment_method == 'card':
        Order.objects.filter(pk=order.pk, user=request.user, status='pending').update(status='paid')
        messages.success(request, 'Навчальну оплату підтверджено.')
    return redirect('profile')

@login_required
@require_POST
def delete_order(request, order_id):
    """Видалення замовлення"""
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    order.delete()
    messages.success(request, 'Замовлення видалено!')
    return redirect('profile')

@login_required
@require_GET
def profile_view(request):
    """Профіль користувача"""
    orders = Order.objects.filter(user=request.user).prefetch_related('items__product').order_by('-created_at')
    return render(request, 'pharmacy/profile.html', {
        'orders': orders,
        'user': request.user
    })

@login_required
@require_POST
def clear_order_history(request):
    """Очищення історії замовлень"""
    Order.objects.filter(user=request.user).delete()
    return redirect('profile')
