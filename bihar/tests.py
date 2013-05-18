from datetime import datetime
from django.http import HttpRequest

from django.test import TestCase
from bihar.reports.due_list import VaccinationSummary
from corehq.apps.users.models import WebUser


class FakeES(object):
    """
    A mock of ES that will return the docs that have been
    added regardless of the query, and some hardcoded
    facets just to sanity check the facet handling code
    """
    
    def __init__(self):
        self.docs = []

    def add_doc(self, id, doc):
        self.docs.append(doc)

    def base_query(self, start=0, size=None):
        return {'filter': {'and': []}}
    
    def run_query(self, query, es_type=None):
        return {
            'hits': {
                'total': len(self.docs),
                'hits': [{'_source': doc} for doc in self.docs]
            },
            'facets': {
                'vaccination_names': {
                    'terms': [
                        {'term': 'foo', 'count': 10}
                    ]
                }
            }
        }


class TestDueList(TestCase):
    """
    Tests the Due List function superficially 
    """
    
    def test_due_list_by_task_name(self):

        fake_request = HttpRequest()
        fake_request.GET = {'group': ''}
        fake_request.couch_user = WebUser(_id='')

        class FakeVaccinationSummary(VaccinationSummary):
            def get_date(self):
                return datetime.utcnow()

        fake_report = FakeVaccinationSummary(request=fake_request)

        es = FakeES()

        due_list = fake_report.due_list_by_task_name(case_es=es)

        self.assertEquals(due_list, [('foo', 10)])
