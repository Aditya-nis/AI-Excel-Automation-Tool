from apps.workspaces.models import WorkspaceMembership

def workspace_context(request):
    """Provides current_workspace and user_workspaces to all templates."""
    if hasattr(request, 'user') and request.user.is_authenticated:
        memberships = WorkspaceMembership.objects.filter(user=request.user).select_related('workspace')
        user_workspaces = [m.workspace for m in memberships]
        return {
            'current_workspace': getattr(request, 'workspace', None),
            'user_workspaces': user_workspaces,
        }
    return {
        'current_workspace': None,
        'user_workspaces': [],
    }
