def cart_context(request):
    cart = request.session.get('cart', {})
    total_count = sum(cart.values())
    return {'cart_total_count': total_count}