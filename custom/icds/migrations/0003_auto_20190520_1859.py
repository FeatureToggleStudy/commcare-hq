# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-05-20 18:59
from __future__ import absolute_import
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('icds', '0002_auto_20190520_1215'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='CCZHostingLink',
            new_name='HostedCCZLink',
        ),
        migrations.RenameModel(
            old_name='CCZHostingSupportingFile',
            new_name='HostedCCZSupportingFile',
        ),
    ]