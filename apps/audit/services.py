from apps.audit.models import AuditEvent

def log_audit(actor=None, event_type="action", description="", workspace=None, object_type="", object_id="", metadata=None, request=None):
    """
    Append-only audit event logging helper.
    Safe against exceptions so audit failures never break business transactions.
    """
    try:
        ip = None
        actor_user = None
        actor_name = "System"
        
        if request:
            if hasattr(request, 'user') and request.user.is_authenticated:
                actor_user = request.user
                actor_name = request.user.username
            ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
            if not workspace and hasattr(request, 'workspace'):
                workspace = request.workspace
        elif actor:
            if hasattr(actor, 'is_authenticated') and actor.is_authenticated:
                actor_user = actor
                actor_name = actor.username
            elif isinstance(actor, str):
                actor_name = actor

        return AuditEvent.objects.create(
            actor=actor_user,
            actor_username=actor_name,
            workspace=workspace,
            event_type=event_type,
            object_type=object_type,
            object_id=str(object_id) if object_id else "",
            description=description,
            metadata=metadata or {},
            ip_address=ip
        )
    except Exception as e:
        # Avoid crashing primary operations if audit fails
        import logging
        logging.getLogger('audit').warning(f"Failed to record audit event: {e}")
        return None
