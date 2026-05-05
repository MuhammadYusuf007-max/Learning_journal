"""Define URL patterns for accounts."""

from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views

from . import views


app_name = 'accounts'

urlpatterns = [
    # Login / logout (use Django's built-in views).
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Password reset flow. We override `success_url` to use namespaced names
    # because `app_name = 'accounts'` puts every URL under the 'accounts:' namespace.
    path(
        'password_reset/',
        auth_views.PasswordResetView.as_view(
            success_url=reverse_lazy('accounts:password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password_reset/done/',
        auth_views.PasswordResetDoneView.as_view(),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            success_url=reverse_lazy('accounts:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(),
        name='password_reset_complete',
    ),

    # Registration page.
    path('register/', views.register, name='register'),
]
