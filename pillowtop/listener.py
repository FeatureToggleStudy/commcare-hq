import logging
from datetime import datetime
import hashlib
import traceback
import simplejson
from gevent import socket
import rawes
import gevent
from django.conf import settings
from dimagi.utils.decorators.memoized import memoized

requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.ERROR)

import couchdbkit

if couchdbkit.version_info < (0, 6, 0):
    USE_NEW_CHANGES = False
else:
    from couchdbkit.changes import ChangesStream

    USE_NEW_CHANGES = True

CHECKPOINT_FREQUENCY = 100
WAIT_HEARTBEAT = 10000


def ms_from_timedelta(td):
    """
    Given a timedelta object, returns a float representing milliseconds
    """
    return (td.seconds * 1000) + (td.microseconds / 1000.0)


class BasicPillow(object):
    couch_filter = None  # string for filter if needed
    document_class = None  # couchdbkit Document class
    changes_seen = 0

    @property
    def couch_db(self):
        return self.document_class.get_db()

    def old_changes(self):
        """
        Couchdbkit < 0.6.0 changes feed listener
        http://couchdbkit.org/docs/changes_consumer.html
        """
        from couchdbkit import Consumer

        c = Consumer(self.couch_db, backend='gevent')
        while True:
            try:
                c.wait(self.parsing_processor, since=self.since, filter=self.couch_filter,
                       heartbeat=WAIT_HEARTBEAT, feed='continuous', timeout=30000)
            except Exception, ex:
                logging.exception("Exception in form listener: %s, sleeping and restarting" % ex)
                gevent.sleep(5)

    def new_changes(self):
        """
        Couchdbkit > 0.6.0 changes feed listener handler (api changes after this)
        http://couchdbkit.org/docs/changes.html
        """
        with ChangesStream(self.couch_db, feed='continuous', heartbeat=True, since=self.since,
                           filter=self.couch_filter) as st:
            for c in st:
                self.processor(c)

    def run(self, since=0):
        """
        Couch changes stream creation
        """
        logging.info("Starting pillow %s" % self.__class__)

        if USE_NEW_CHANGES:
            self.new_changes()
        else:
            self.old_changes()

    def get_name(self):
        return "%s.%s" % (self.__module__, self.__class__.__name__)

    def get_checkpoint_doc_name(self):
        return "pillowtop_%s" % self.get_name()

    def get_checkpoint(self):
        doc_name = self.get_checkpoint_doc_name()

        if self.couch_db.doc_exist(doc_name):
            checkpoint_doc = self.couch_db.open_doc(doc_name)
        else:
            checkpoint_doc = {
                "_id": doc_name,
                "seq": "0"
                #todo: bigcouch changes seq are [num, string] arrs, num is meaningless,string is meaningful
            }
            self.couch_db.save_doc(checkpoint_doc)
        return checkpoint_doc

    def reset_checkpoint(self):
        checkpoint_doc = self.get_checkpoint()
        checkpoint_doc['old_seq'] = checkpoint_doc['seq']
        checkpoint_doc['seq'] = "0"
        self.couch_db.save_doc(checkpoint_doc)


    @property
    def since(self):
        checkpoint = self.get_checkpoint()
        return checkpoint['seq']

    def set_checkpoint(self, change):
        checkpoint = self.get_checkpoint()
        checkpoint['seq'] = change['seq']
        self.couch_db.save_doc(checkpoint)

    def parsing_processor(self, change):
        """
        Processor that also parses the change to json - only for pre 0.6.0 couchdbkit,
        as the change is passed as a string
        """
        self.processor(simplejson.loads(change))

    def processor(self, change, do_set_checkpoint=True):
        """
        Parent processsor for a pillow class - this should not be overridden.
        This workflow is made for the situation where 1 change yields 1 transport/transaction
        """
        self.changes_seen += 1
        if self.changes_seen % CHECKPOINT_FREQUENCY == 0 and do_set_checkpoint:
            logging.info(
                "(%s) setting checkpoint: %s" % (self.get_checkpoint_doc_name(), change['seq']))
            self.set_checkpoint(change)

        try:
            t = self.change_trigger(change)
            if t is not None:
                tr = self.change_transform(t)
                if tr is not None:
                    self.change_transport(tr)
        except Exception, ex:
            logging.error("Error on change: %s, %s" % (change['id'], ex))


    def change_trigger(self, changes_dict):
        """
        Step one of pillowtop process
        For a given _changes indicator, the changes dict (the id, _rev) is sent here.

        Note, a couch _changes line is: {'changes': [], 'id': 'guid',  'seq': <int>}
        a 'deleted': True might be there too

        whereas a doc_dict is _id
        Should return a doc_dict
        """
        if changes_dict.get('deleted', False):
            #override deleted behavior on consumers that care/deal with deletions
            return None
        return self.couch_db.open_doc(changes_dict['id'])

    def change_transform(self, doc_dict):
        """
        Step two of the pillowtop processor:
        Process/transform doc_dict if needed - by default, return the doc_dict passed.
        """
        return doc_dict


    def change_transport(self, doc_dict):
        """
        Step three of the pillowtop processor:
        Finish transport of doc if needed. Your subclass should implement this
        """
        raise NotImplementedError(
            "Error, this pillowtop subclass has not been configured to do anything!")


class ElasticPillow(BasicPillow):
    """
    Elasticsearch handler
    """
    es_host = ""
    es_port = ""
    es_index = ""
    es_type = ""
    es_meta = {}
    es_timeout = 30 # in seconds
    bulk = False

    # Note - we allow for for existence because we do not care - we want the ES
    # index to always have the latest version of the case based upon ALL changes done to it.
    allow_updates = True

    def __init__(self, create_index=True):
        """
        create_index if the index doesn't exist on the ES cluster
        """
        if create_index:
            if not self.index_exists():
                self.create_index()

    def index_exists(self):
        es = self.get_es()
        return es.head(self.es_index)

    def get_doc_path(self, doc_id):
        return "%s/%s/%s" % (self.es_index, self.es_type, doc_id)

    def get_index_mapping(self):
        es = self.get_es()
        return es.get('%s/_mapping' % self.es_index).get(self.es_index, {})

    def set_mapping(self, type_string, mapping):
        es = self.get_es()
        return es.put("%s/%s/_mapping" % (self.es_index, type_string), data=mapping)

    @memoized
    def get_es(self):
        return rawes.Elastic('%s:%s' % (self.es_host, self.es_port, self.es_timeout))

    def delete_index(self):
        """
        Coarse way of deleting an index - a todo is to set aliases where need be
        """
        es = self.get_es()
        if es.head(self.es_index):
            es.delete(self.es_index)

    def create_index(self):
        """
        Rebuild an index after a delete
        """
        es = self.get_es()
        es.put(self.es_index, data=self.es_meta)

    def change_trigger(self, changes_dict):
        if changes_dict.get('deleted', False):
            try:
                self.get_es().delete(path=self.get_doc_path(changes_dict['id']))
            except Exception, ex:
                logging.error("ElasticPillow: error deleting route %s - ignoring: %s" % \
                              (self.get_doc_path(changes_dict['id']), ex))
            return None
        return self.couch_db.open_doc(changes_dict['id'])


    def doc_exists(self, doc_id):
        """
        Using the HEAD 404/200 result API for document existence
        Returns True if 200(exists)
        """
        es = self.get_es()
        doc_path = self.get_doc_path(doc_id)
        head_result = es.head(doc_path)
        return head_result

    def bulk_builder(self, changes):
        """
        http://www.elasticsearch.org/guide/reference/api/bulk.html
        bulk loader follows the following:
        { "index" : { "_index" : "test", "_type" : "type1", "_id" : "1" } }\n
        { "field1" : "value1" }\n
        """
        for change in changes:
            try:
                t = self.change_trigger(change)
                if t is not None:
                    tr = self.change_transform(t)
                    if tr is not None:
                        self.change_transport(tr)

                        yield {
                        "index": {"_index": self.es_index, "_type": self.es_type, "_id": tr['_id']}}
                        yield tr
            except Exception, ex:
                logging.error("Error on change: %s, %s" % (change['id'], ex))

    def process_bulk(self, changes):
        self.allow_updates = False
        self.bulk = True
        es = self.get_es()
        bulk_payload = '\n'.join(map(simplejson.dumps, self.bulk_builder(changes))) + "\n"
        es.post('_bulk', data=bulk_payload)


    def processor(self, change, do_set_checkpoint=True):
        """
        Parent processsor for a pillow class - this should not be overridden.
        This workflow is made for the situation where 1 change yields 1 transport/transaction
        """
        self.changes_seen += 1
        if self.changes_seen % CHECKPOINT_FREQUENCY == 0 and do_set_checkpoint:
            logging.info(
                "(%s) setting checkpoint: %s" % (self.get_checkpoint_doc_name(), change['seq']))
            self.set_checkpoint(change)

        try:
            t = self.change_trigger(change)
            if t is not None:
                tr = self.change_transform(t)
                if tr is not None:
                    self.change_transport(tr)
        except Exception, ex:
            logging.error("Error on change: %s, %s" % (change['id'], ex))


    def change_transport(self, doc_dict):
        """
        Default elastic pillow for a given doc to a type.
        """
        try:
            es = self.get_es()
            doc_path = self.get_doc_path(doc_dict['_id'])

            if self.allow_updates:
                can_put = True
            else:
                can_put = not self.doc_exists(doc_dict['_id'])

            if can_put and not self.bulk:
                res = es.put(doc_path, data=doc_dict)
                if res.get('status', 0) == 400:
                    logging.error(
                        "Pillowtop Error [%s]:\n%s\n\tDoc id: %s\n\t%s" % (self.get_name(),
                                                                           res.get('error',
                                                                                   "No error message"),
                                                                           doc_dict['_id'],
                                                                           doc_dict.keys()))
        except Exception, ex:
            logging.error("PillowTop [%s]: transporting change data to elasticsearch error: %s",
                          (self.get_name(), ex))
            return None


class AliasedElasticPillow(ElasticPillow):
    """
    This pillow class defines it as being alias-able. That is, when you query it, you use an Alias to access it.

    This could be for varying reasons -  to make an index by certain metadata into its own index for performance/separation reasons

    Or, for our initial use case, needing to version/update the index mappings on the fly with minimal disruption.


    The workflow for altering an AliasedElasticPillow is that if you know you made a change, the pillow will create a new
    Index witha new md5sum as its suffix. Once it's finished indexing, you will need to flip the alias over to it.
    """
    es_alias = ''
    es_index_prefix = ''
    seen_types = {}
    es_index = ""

    def check_alias(self):
        """
        Naive means to verify the alias of the current pillow iteration is matched.
        If we go fancier with routing and multi-index aliases due to index splitting, this will need to be revisited.
        """
        es = self.get_es()
        aliased_indexes = es[self.es_alias].get('_aliases')
        return aliased_indexes.keys()

    def calc_mapping_hash(self, mapping):
        return hashlib.md5(simplejson.dumps(mapping, sort_keys=True)).hexdigest()


    def __init__(self, **kwargs):
        super(AliasedElasticPillow, self).__init__(**kwargs)
        self.seen_types = self.get_index_mapping()
        logging.info("Pillowtop [%s] Retrieved mapping from ES" % self.get_name())

    def calc_meta(self):
        raise NotImplementedError("Need to implement your own meta calculator")


    def bulk_builder(self, changes):
        """
        http://www.elasticsearch.org/guide/reference/api/bulk.html
        bulk loader follows the following:
        { "index" : { "_index" : "test", "_type" : "type1", "_id" : "1" } }\n
        { "field1" : "value1" }\n
        """
        for change in changes:
            try:
                t = self.change_trigger(change)
                if t is not None:
                    tr = self.change_transform(t)
                    if tr is not None:
                        self.change_transport(tr)

                        yield {"index": {"_index": self.es_index, "_type": self.get_type_string(tr),
                                         "_id": tr['_id']}}
                        yield tr
            except Exception, ex:
                logging.error("Error on change: %s, %s" % (change['id'], ex))


    def type_exists(self, doc_dict, server=False):
        """
        Verify whether the server has indexed this type

        We can assume at startup that the mapping from the server is loaded,
        so in memory will be up to date.

        server = False:
            if true, override to always call server
        """
        es = self.get_es()
        type_string = self.get_type_string(doc_dict)

        ##################
        #ES 0.20 has the index HEAD API.  While we're on 0.19, we will need to poll the index
        # metadata
        if server:
            type_path = "%(index)s/%(type_string)s" % (
            {'index': self.es_index, 'type_string': type_string, })
            head_result = es.head(type_path)
            self.seen_types[type_string] = head_result
            return head_result
            ##################

        #####
        #0.19 method, get the mapping from the index
        return self.seen_types.has_key(type_string)

    def get_type_string(self, doc_dict):
        raise NotImplementedError("Please implement acustom type string resolver")

    def get_doc_path_typed(self, doc_dict):
        return "%(index)s/%(type_string)s/%(id)s" % (
            {
                'index': self.es_index,
                'type_string': self.get_type_string(doc_dict),
                'id': doc_dict['_id']
            })

    def doc_exists(self, doc_dict):
        """
        Overrided based upon the doc type
        """
        es = self.get_es()
        head_result = es.head(self.get_doc_path_typed(doc_dict))
        return head_result


    def assume_alias(self):
        """
        todo: for this instance, have the index that represents this index
        receive the alias itself as well.
        This presents a management issue later if we route out additional
        indexes/aliases that we automate this carefully.
        """
        pass

    def get_name(self):
        """
        Gets the doc_name in which to set the checkpoint for itself, based upon
        class name and the hashed name representation.
        """
        return "%s.%s.%s" % (self.__module__, self.__class__.__name__, self.calc_meta())

    def get_mapping_from_type(self, doc_dict):
        raise NotImplementedError("This must be implemented in this subclass!")

    def change_transport(self, doc_dict):
        """
        Override the elastic transport to go to the index + the type being a string between the
        domain and case type
        """
        #        start = datetime.utcnow()
        try:
            es = self.get_es()
            if not self.type_exists(doc_dict):
                #if type is never seen, apply mapping for said type
                type_mapping = self.get_mapping_from_type(doc_dict)
                #update metadata
                type_mapping[self.get_type_string(doc_dict)]['_meta'][
                    'created'] = datetime.isoformat(datetime.utcnow())
                mapping_res = self.set_mapping(self.get_type_string(doc_dict), type_mapping)
                if mapping_res.get('ok', False) and mapping_res.get('acknowledged', False):
                    #API confirms OK, trust it.
                    logging.info(
                        "Mapping set: [%s] %s" % (self.get_type_string(doc_dict), mapping_res))
                    #manually update in memory dict
                    self.seen_types[self.get_type_string(doc_dict)] = {}

                #            got_type = datetime.utcnow()
            doc_path = self.get_doc_path_typed(doc_dict)

            if self.allow_updates:
                can_put = True
            else:
                can_put = not self.doc_exists(doc_dict)

            if can_put and not self.bulk:
                res = es.put(doc_path, data=doc_dict)
                #                did_put = datetime.utcnow()
                if res.get('status', 0) == 400:
                    logging.error(
                        "Pillowtop Error [%(case_type)s]:\n%(es_message)s\n\tDoc id: %(doc_id)s\n\t%(doc_keys)s" % dict(
                            case_type=self.get_name(),
                            es_message=res.get('error', "No error message"),
                            doc_id=doc_dict['_id'],
                            doc_keys=doc_dict.keys()))
        except Exception, ex:
            tb = traceback.format_exc()
            logging.error(
                "PillowTop [%s]: transporting change data doc_id: %s to elasticsearch error: %s\ntraceback: %s\n" % (
                self.get_name(), doc_dict['_id'], ex, tb))
            return None


class NetworkPillow(BasicPillow):
    """
    Basic network endpoint handler.
    This is useful for the logstash/Splunk use cases.
    """
    endpoint_host = ""
    endpoint_port = 0
    transport_type = 'tcp'

    def change_transport(self, doc_dict):
        try:
            address = (self.endpoint_host, self.endpoint_port)
            if self.transport_type == 'tcp':
                stype = socket.SOCK_STREAM
            elif self.transport_type == 'udp':
                stype = socket.SOCK_DGRAM
            sock = socket.socket(type=stype)
            sock.connect(address)
            sock.send(simplejson.dumps(doc_dict), timeout=1)
            return 1
        except Exception, ex:
            logging.error(
                "PillowTop [%s]: transport to network socket error: %s" % (self.get_name(), ex))
            return None


class LogstashMonitoringPillow(NetworkPillow):
    """
    This is a logstash endpoint (but really just TCP) for our production monitoring/aggregation
    of log information.
    """

    def __init__(self):
        if settings.DEBUG:
            #In a dev environment don't care about these
            logging.info(
                "[%s] Settings are DEBUG, suppressing the processing of these feeds" % self.get_name())

    def processor(self, change):
        if settings.DEBUG:
            return {}
        else:
            return super(NetworkPillow, self).processor(change)

