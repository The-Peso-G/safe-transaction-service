from django.conf.urls import url
from django.urls import path

from . import views

app_name = "safe"

timestamp_regex = '\\d{4}[-]?\\d{1,2}[-]?\\d{1,2} \\d{1,2}:\\d{1,2}:\\d{1,2}'

urlpatterns = [
    url(r'^about/$', views.AboutView.as_view(), name='about'),
    path('safes/<str:address>/transactions/', views.SafeMultisigTransactionListView.as_view(),
         name='multisig-transactions'),
    path('safes/<str:address>/incoming-transactions/', views.SafeIncomingTxListView.as_view(),
         name='incoming-transactions'),
    path('safes/<str:address>/module-transactions/', views.SafeModuleTransactionListView.as_view(),
         name='module-transactions'),
    path('safes/<str:address>/creation/', views.SafeCreationView.as_view(),
         name='safe-creation'),
    path('safes/<str:address>/balances/', views.SafeBalanceView.as_view(),
         name='safe-balances'),
    path('safes/<str:address>/balances/usd/', views.SafeBalanceUsdView.as_view(),
         name='safe-balances-usd'),
    path('transactions/<str:tx_hash>/', views.SafeMultisigTransactionDetailView.as_view(),
         name='multisig-transaction'),
    path('owners/<str:address>/', views.OwnersView.as_view(),
         name='owners'),
]
