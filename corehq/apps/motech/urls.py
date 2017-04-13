from django.conf.urls import url
from corehq.apps.motech.views import OpenmrsInstancesMotechView, \
    OpenmrsConceptMotechView

urlpatterns = [
    url('^openmrs/servers/$',
        OpenmrsInstancesMotechView.as_view(), name=OpenmrsInstancesMotechView.urlname),
    url('^openmrs/metadata/$',
        OpenmrsConceptMotechView.as_view(), name=OpenmrsConceptMotechView.urlname),
]
