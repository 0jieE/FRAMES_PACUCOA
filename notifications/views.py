from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from frames_project.utils import paginate


@login_required
def notification_list(request):
    qs = request.user.notifications.all()
    show = request.GET.get("show", "all")
    if show == "unread":
        qs = qs.filter(is_read=False)
    return render(request, "notifications/list.html", {"page_obj": paginate(request, qs, 20), "show": show})


@login_required
@require_POST
def mark_read(request, pk):
    notification = get_object_or_404(request.user.notifications, pk=pk)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    if request.POST.get("open") and notification.link and url_has_allowed_host_and_scheme(
        notification.link, allowed_hosts={request.get_host()}
    ):
        return redirect(notification.link)
    return redirect("notifications:list")


@login_required
@require_POST
def mark_all_read(request):
    count = request.user.notifications.filter(is_read=False).update(is_read=True)
    messages.success(request, f"{count} notification(s) marked as read.")
    return redirect("notifications:list")
