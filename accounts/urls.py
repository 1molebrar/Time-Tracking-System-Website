from django.urls import path
from . import views

# Accounts app URL patterns
urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/add/', views.employee_add, name='employee_add'),
    path('employees/<int:user_id>/edit/', views.employee_edit, name='employee_edit'),
    path('employees/<int:user_id>/deactivate/', views.employee_deactivate, name='employee_deactivate'),
    path('employees/<int:user_id>/activate/', views.employee_activate, name='employee_activate'),
]
