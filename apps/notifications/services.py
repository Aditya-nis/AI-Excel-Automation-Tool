from apps.notifications.models import Notification

def notify_user(recipient, title, message, level='info', workspace=None, link_url=''):
    """Delivers in-app notification without leaking sensitive secrets."""
    try:
        return Notification.objects.create(
            recipient=recipient,
            workspace=workspace,
            title=title,
            message=message,
            level=level,
            link_url=link_url
        )
    except Exception as e:
        import logging
        logging.getLogger('notifications').warning(f"Notification delivery failed: {e}")
        return None
