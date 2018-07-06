from __future__ import absolute_import
from __future__ import unicode_literals
from memoized import memoized

from corehq.apps.reports.standard import MonthYearMixin
from custom.intrahealth.filters import YeksiNaaLocationFilter2, FRMonthFilter, FRYearFilter
from custom.intrahealth.sqldata import RecapPassageData2, DateSource2
from custom.intrahealth.reports.tableu_de_board_report_v2 import MultiReport


class RecapPassageReport2(MonthYearMixin, MultiReport):
    title = "Recap Passage NEW"
    name = "Recap Passage NEW"
    slug = 'recap_passage2'
    report_title = "Recap Passage"
    exportable = True
    default_rows = 10
    fields = [FRMonthFilter, FRYearFilter, YeksiNaaLocationFilter2]

    @property
    @memoized
    def data_providers(self):
        dates = DateSource2(config=self.report_config).rows
        data_providers = []
        for date in dates:
            config = self.report_config
            config.update(dict(startdate=date, enddate=date))
            data_providers.append(RecapPassageData2(config=config))
        if not data_providers:
            data_providers.append(RecapPassageData2(config=self.report_config))
        return data_providers
