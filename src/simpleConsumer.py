import confluent_kafka
import datetime
import logging
import json
import traceback
import threading

CONFLUENT_KAFKA_CONSUMER_DEFAULTS = {
    'default.topic.config': {
        'auto.offset.reset': 'largest'
    }
}

def value_deserializer(value):    
    return json.loads(value)

class Consumer(object):
    def __init__(self, **kwargs):
        kwargs = {**CONFLUENT_KAFKA_CONSUMER_DEFAULTS,**kwargs}
        self.topics = kwargs.get('subscribe.topics')
        del kwargs['subscribe.topics']
        if 'value.deserializer' in kwargs:
            self.value_deserializer = kwargs.get('value.deserializer')
            del kwargs['value.deserializer']  
        self._consumer_kwargs = kwargs
        self._consumer = None
        self._processing = threading.Event()
        self._started = threading.Event()
        self._lock = threading.Lock()

    def clone(self):
        consumer = Consumer(**{**self._consumer_kwargs, ** {
            'subscribe.topics' : self.topics
        }})
        consumer.value_deserializer = value_deserializer
        return consumer

    def on_assign(self, consumer, partitions, start_event):
        logging.debug("{} {} {}".format('on_assign:', len(partitions), 'partitions:'))
        for p in partitions:
            logging.debug(' %s [%d] @ %d' % (p.topic, p.partition, p.offset))
        consumer.assign(partitions)
        if start_event:
            start_event.set()

    def on_revoke(self, consumer, partitions):
        logging.debug("{} {} {}".format('on_revoke:', len(partitions), 'partitions:'))
        for p in partitions:
            logging.debug(' %s [%d] @ %d' % (p.topic, p.partition, p.offset))
        consumer.unassign()

    def start(self, start_event = None):
        if self._started.is_set():
            return
        if self._consumer:
            self._started.wait()
            return
        self._lock.acquire()
        try:
            self._consumer = confluent_kafka.Consumer(**self._consumer_kwargs)
            self._consumer.subscribe(self.topics,
                on_assign=lambda consumer, partitions: self.on_assign(consumer, partitions, start_event), 
                on_revoke=self.on_revoke)
            self._started.set()
        finally:
            self._lock.release()

    def start_process(self, stop_event, callback, start_event = None):
        if self._processing.is_set():
            return
        if not self._consumer:
            self.start(start_event=start_event)
        self.process(stop_event, callback)

    def consume(self, stop_event, callback, start_event = None):
        if self._processing.is_set():
            return
        if not self._consumer:
            self.start(start_event=start_event)
        try:
            self.process(stop_event, callback)
        finally:
            self.stop()

    def stop(self):
        self._processing.clear()
        self._lock.acquire()
        try:
            if self._started.is_set():
                self._started.clear()
                self._consumer.close()
                self._consumer = None
        finally:
            self._lock.release()
        
    def process(self, stop_event, callback):
        if self._processing.is_set():
            return
        try:
            self._processing.set()
            while self._processing.is_set() and not stop_event.is_set():
                msg = self._consumer.poll(.1)                
                if msg is None:
                    continue        
                if msg.error():
                    if msg.error().code() == confluent_kafka.KafkaError._PARTITION_EOF:
                        continue
                    else:
                        print(msg.error())
                        break    
                
                assert msg.timestamp()[0] == confluent_kafka.TIMESTAMP_CREATE_TIME
                msg_timestamp = None
                try:
                    msg_timestamp = datetime.datetime.fromtimestamp(float(msg.timestamp()[1]))
                except ValueError:
                    msg_timestamp = datetime.datetime.min
                
                value = msg.value()
                if hasattr(self, 'value_deserializer'):            
                    value = self.value_deserializer(value)       
                callback(**{
                    "topic" : msg.topic(),
                    "partition" : msg.partition(),
                    "key" : msg.key().decode("utf-8") ,
                    "headers" :  msg.headers(),
                    "value" : value,
                    "timestamp" : msg_timestamp,
                    "rec_timestamp" : datetime.datetime.now()
                })
        except:
            logging.error("Error consuming requests")    
            logging.error(traceback.format_exc())
        finally:
            self._processing.clear()           
    
