from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.notifications.models import Notification
from apps.notifications.services import notify_user

User = get_user_model()

class NotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='notify_user', password='password123')

    def test_notify_user(self):
        notif = notify_user(
            recipient=self.user,
            title="Data Quality Alert",
            message="Null rates exceeded 15% threshold.",
            level="warning",
            link_url="/quality/"
        )
        self.assertIsNotNone(notif)
        self.assertEqual(notif.recipient, self.user)
        self.assertEqual(notif.level, 'warning')
        self.assertFalse(notif.is_read)

        # Mark read
        notif.is_read = True
        notif.save()
        self.assertTrue(Notification.objects.get(id=notif.id).is_read)
