from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.accounts.forms import CustomUserCreationForm
from apps.audit.services import log_audit

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            log_audit(actor=user, event_type="auth.register", description=f"Registered user '{user.username}'", request=request)
            messages.success(request, f"Welcome to AI Power BI, {user.username}!")
            return redirect('dashboard')
    else:
        form = CustomUserCreationForm()
    return render(request, 'accounts/register.html', {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            log_audit(actor=user, event_type="auth.login", description=f"User '{user.username}' logged in", request=request)
            messages.success(request, "Logged in successfully.")
            next_url = request.GET.get('next') or 'dashboard'
            return redirect(next_url)
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})

def logout_view(request):
    if request.user.is_authenticated:
        log_audit(actor=request.user, event_type="auth.logout", description=f"User '{request.user.username}' logged out", request=request)
        logout(request)
        messages.info(request, "Logged out successfully.")
    return redirect('login')

@login_required
def password_change_view(request):
    """Allows users to safely change their login password directly from Django UI."""
    if request.method == 'POST':
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            # Prevent user session invalidation after password update
            update_session_auth_hash(request, user)
            log_audit(actor=user, event_type="auth.password_change", description=f"Password updated for user '{user.username}'", request=request)
            messages.success(request, "Your password has been changed successfully!")
            return redirect('password_change')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PasswordChangeForm(user=request.user)
    return render(request, 'accounts/password_change.html', {'form': form})
