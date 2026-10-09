from django.utils import timezone
from apps.approvals.models import ApprovalRequest
from apps.notifications.services import notify_user
from apps.audit.services import log_audit

def request_approval(workspace, requester, request_type, title, description, target_type='', target_id=''):
    """Creates a formal approval request."""
    req = ApprovalRequest.objects.create(
        workspace=workspace,
        requester=requester,
        request_type=request_type,
        title=title,
        description=description,
        target_object_type=target_type,
        target_object_id=str(target_id)
    )

    # Notify workspace admins / owner
    if workspace.owner and workspace.owner != requester:
        notify_user(
            recipient=workspace.owner,
            workspace=workspace,
            title=f"Approval Required: {title}",
            message=f"{requester.username} submitted an approval request for {request_type}.",
            level='warning',
            link_url='/approvals/'
        )

    log_audit(
        actor=requester,
        event_type="approval.requested",
        description=f"Requested approval for '{title}' ({request_type})",
        workspace=workspace,
        object_type="ApprovalRequest",
        object_id=req.id
    )

    return req

def decide_approval(approval_request, reviewer, action='approved', comments=''):
    """Processes decision on approval request."""
    if action not in ['approved', 'rejected']:
        raise ValueError("Action must be 'approved' or 'rejected'")

    approval_request.status = action
    approval_request.reviewed_by = reviewer
    approval_request.review_comments = comments
    approval_request.reviewed_at = timezone.now()
    approval_request.save()

    # Notify requester
    notify_user(
        recipient=approval_request.requester,
        workspace=approval_request.workspace,
        title=f"Approval {action.title()}: {approval_request.title}",
        message=f"{reviewer.username} {action} your request. Comments: {comments or 'None'}",
        level='success' if action == 'approved' else 'critical',
        link_url='/approvals/'
    )

    log_audit(
        actor=reviewer,
        event_type=f"approval.{action}",
        description=f"Decision '{action}' on '{approval_request.title}' by {reviewer.username}",
        workspace=approval_request.workspace,
        object_type="ApprovalRequest",
        object_id=approval_request.id,
        metadata={"comments": comments}
    )

    return approval_request
