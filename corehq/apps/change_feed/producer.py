from __future__ import unicode_literals
from __future__ import absolute_import
import json

from django.conf import settings
from kafka import KafkaProducer

from corehq.util.soft_assert import soft_assert


class ChangeProducer(object):

    def __init__(self):
        self._producer = None

    @property
    def producer(self):
        if self._producer is not None:
            return self._producer

        self._producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BROKERS,
            api_version=settings.KAFKA_API_VERSION,
            client_id="cchq-producer",
            retries=3,
            acks=1,
            key_serializer=lambda key: key.encode()
        )
        return self._producer

    def send_change(self, topic, change_meta):
        message = change_meta.to_json()
        try:
            self.producer.send(topic, bytes(json.dumps(message)), key=change_meta.document_id)
            self.producer.flush()
        except Exception as e:
            _assert = soft_assert(notify_admins=True)
            _assert(False, 'Problem sending change to kafka {}: {} ({})'.format(
                message, e, type(e)
            ))
            raise


producer = ChangeProducer()
