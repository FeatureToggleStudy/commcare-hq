# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-01-15 19:47
from __future__ import absolute_import, unicode_literals

from django.db import migrations

from corehq.sql_db.operations import RawSQLMigration

migrator = RawSQLMigration(('custom', 'icds_reports', 'migrations', 'sql_templates'))


class Migration(migrations.Migration):

    dependencies = [
        ('icds_reports', '0030_auto_20171128_0042'),
    ]

    operations = [
        migrator.get_migration('update_tables15.sql'),
    ]
