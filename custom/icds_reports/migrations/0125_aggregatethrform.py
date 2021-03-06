# Generated by Django 1.11.20 on 2019-06-21 09:49

from django.db import migrations, models

import custom.icds_reports.models.aggregate


class Migration(migrations.Migration):

    dependencies = [
        ('icds_reports', '0124_update_agg_awc_view'),
    ]

    operations = [
        migrations.CreateModel(
            name='AggregateTHRForm',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('state_id', models.TextField()),
                ('supervisor_id', models.TextField()),
                ('awc_id', models.TextField()),
                ('month', models.DateField()),
                ('thr_distribution_image_count', models.IntegerField(help_text='Count of Images clicked per awc')),
            ],
            options={
                'db_table': 'icds_dashboard_thr_v2',
            },
            bases=(models.Model, custom.icds_reports.models.aggregate.AggregateMixin),
        ),
    ]
