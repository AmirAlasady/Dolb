from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.views.static import serve
from django.conf import settings

# Protected media view
def protected_media_view(request, path):
    if not request.user.is_authenticated:
        return HttpResponse('Unauthorized', status=401)
    # Add additional permission checks here if needed
    return serve(request, path, document_root=settings.MEDIA_ROOT)
