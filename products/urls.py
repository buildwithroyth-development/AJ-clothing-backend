from django.urls import re_path

from . import views

# The trailing slash is optional so '/products' and '/products/' both work
# (a redirect would break cross-origin requests that carry an Authorization header).
urlpatterns = [
    re_path(r'^categories/?$', views.CategoryList.as_view()),
    re_path(r'^products/?$', views.ProductList.as_view()),
    re_path(r'^products/(?P<pid>[^/]+)/restock/?$', views.ProductRestock.as_view()),
    re_path(r'^products/(?P<pid>[^/]+)/history/?$', views.ProductHistory.as_view()),
    re_path(r'^products/(?P<pid>[^/]+)/?$', views.ProductDetail.as_view()),
    re_path(r'^sales/?$', views.SaleList.as_view()),
    re_path(r'^sales/(?P<sale_id>[^/]+)/?$', views.SaleDetail.as_view()),
    re_path(r'^(?:stock_movements|movements)/?$', views.StockMovementList.as_view()),
]
