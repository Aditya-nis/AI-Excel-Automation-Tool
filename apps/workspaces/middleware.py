from apps.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole

class WorkspaceMiddleware:
    """Ensures every authenticated request has an active Workspace attached."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.workspace = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            workspace_id = request.session.get('active_workspace_id') or request.META.get('HTTP_X_WORKSPACE_ID')
            workspace = None
            if workspace_id:
                try:
                    membership = WorkspaceMembership.objects.filter(user=request.user, workspace_id=workspace_id).first()
                    if membership:
                        workspace = membership.workspace
                except Exception:
                    workspace = None
            
            if not workspace:
                # Find default or first membership
                membership = (
                    WorkspaceMembership.objects.filter(user=request.user, is_default=True).first()
                    or WorkspaceMembership.objects.filter(user=request.user).first()
                )
                if membership:
                    workspace = membership.workspace
                else:
                    # Create default workspace for new user
                    workspace = Workspace.objects.create(
                        name=f"{request.user.username}'s Workspace",
                        owner=request.user,
                        description="Default workspace for analytics and MIS reporting."
                    )
                    WorkspaceMembership.objects.create(
                        workspace=workspace,
                        user=request.user,
                        role=WorkspaceRole.ADMIN,
                        is_default=True
                    )
            
            request.workspace = workspace
            if workspace and request.session.get('active_workspace_id') != workspace.id:
                request.session['active_workspace_id'] = workspace.id

        return self.get_response(request)
