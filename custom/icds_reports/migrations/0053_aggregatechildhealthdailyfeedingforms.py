# -*- coding: utf-8 -*-
# flake8: noqa
# Generated by Django 1.11.13 on 2018-06-19 18:41
from __future__ import absolute_import
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('icds_reports', '0052_inactiveawws_icdsfile'),
    ]

    operations = [
        migrations.CreateModel(
            name='AggregateChildHealthDailyFeedingForms',
            fields=[
                ('state_id', models.CharField(max_length=40)),
                ('month', models.DateField(help_text='Will always be YYYY-MM-01')),
                ('case_id', models.CharField(max_length=40, primary_key=True, serialize=False)),
                ('latest_time_end_processed', models.DateTimeField(help_text='The latest form.meta.timeEnd that has been processed for this case')),
                ('sum_attended_child_ids', models.PositiveSmallIntegerField(help_text='Number of days the child has attended this month', null=True)),
            ],
            options={
                'db_table': 'icds_dashboard_daily_feeding_forms',
            },
        ),
    ]
