from rest_framework.routers import DefaultRouter
from files.views import FileViewSet

router = DefaultRouter()
router.register(r"files", FileViewSet, basename="file")

urlpatterns = router.urls
