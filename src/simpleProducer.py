import confluent_kafka
import datetime
import logging
import json
import uuid

CONFLUENT_KAFKA_PRODUCER_DEFAULTS = {
}

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, (uuid.UUID)):
        return str(obj)
    raise TypeError ("Type %s not serializable" % type(obj))

def value_serializer(value):    
    return json.dumps(value, ensure_ascii=False, default=json_serial)

class Producer(object):
    def __init__(self, **kwargs):
        kwargs = {**CONFLUENT_KAFKA_PRODUCER_DEFAULTS,**kwargs}
        if 'send.topic' in kwargs:
            self.default_topic = kwargs.get('send.topic')
            del kwargs['send.topic']  
        if 'value.serializer' in kwargs:
            self.value_serializer = kwargs.get('value.serializer')
            del kwargs['value.serializer']
        self.auto_flush = True
        if 'send.flush' in kwargs:
            self.auto_flush = kwargs.get('send.flush')
            del kwargs['send.flush']
        self.producer = confluent_kafka.Producer(**kwargs)

    def send(self, value, topic=None, partition=None, key=None, headers=None):
        self.producer.poll(0)
        if hasattr(self, 'value_serializer'):            
            value = self.value_serializer(value)
        if isinstance(key, uuid.UUID):
            key = str(key)
        if not topic:
            topic = self.default_topic
        kwargs = {
            "topic" : topic,
            "value" : value,
            "timestamp" : int(datetime.datetime.now().timestamp()),
            "callback" : Producer._delivery_report,
            "key" : key            
        }
        if partition:
            kwargs['partition'] = partition
        if headers:
            kwargs['headers'] = headers

        self.producer.produce(**kwargs)
        if self.auto_flush:
            self.producer.flush()

    @staticmethod
    def _delivery_report(err, msg):
        """ Called once for each message produced to indicate delivery result.
            Triggered by poll() or flush(). """
        if err is not None:
            logging.warn('Message delivery failed: {}'.format(err))
        else:
            logging.debug('Message delivered to {} [{}]'.format(msg.topic(), msg.partition()))