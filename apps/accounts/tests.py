from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='OldPassword123!')
        self.client = Client()

    def test_password_change_requires_login(self):
        response = self.client.get(reverse('password_change'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_password_change_success(self):
        self.client.login(username='testuser', password='OldPassword123!')
        response = self.client.post(reverse('password_change'), {
            'old_password': 'OldPassword123!',
            'new_password1': 'NewSecurePassword456!',
            'new_password2': 'NewSecurePassword456!',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your password has been changed successfully!")
        
        # Verify old password no longer works
        self.client.logout()
        login_fail = self.client.login(username='testuser', password='OldPassword123!')
        self.assertFalse(login_fail)

        # Verify new password works
        login_success = self.client.login(username='testuser', password='NewSecurePassword456!')
        self.assertTrue(login_success)
