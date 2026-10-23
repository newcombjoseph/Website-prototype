from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('shop/', views.catalog, name='catalog'),
    path('products/<slug:slug>/', views.product, name='product'),
    path('cart/', views.cart, name='cart'),
    path('cart/add/', views.cart_add, name='cart_add'),
    path('cart/update/', views.cart_update, name='cart_update'),
    path('checkout/', views.checkout, name='checkout'),
    path('checkout/start/', views.checkout_start, name='checkout_start'),
    path('checkout/complete/', views.checkout_complete, name='checkout_complete'),
    path('checkout/cancel/', views.checkout_cancel, name='checkout_cancel'),
    path('about/', views.about, name='about'),
    path('shipping/', views.shipping, name='shipping'),
    path('robots.txt', views.robots),
]
