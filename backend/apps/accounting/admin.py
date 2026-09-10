from django.contrib import admin

from .models import Invoice, SyncCheckpoint, SyncRun, Transaction

admin.site.register([Invoice, Transaction, SyncRun, SyncCheckpoint])
