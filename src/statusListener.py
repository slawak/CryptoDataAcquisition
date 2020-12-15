import json
import uuid
import logging
import threading
import traceback



class StatusListener(object):
    listeners = {}

    def __init__(self, status_consumer, timeout, 
            request_id = None, 
            processor_id = None,
            key_property = None, keys = None):
        self.id = uuid.uuid1()
        self._consumer = status_consumer
        self._timeout = timeout
        self._configured = threading.Event()
        self._start_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread = None
        self._thread_start_event = threading.Event()
        self.configure(request_id, processor_id, key_property, keys)                
        StatusListener.listeners[self.id] = self
    
    def start(self, wait = False):
        if not self._thread_start_event.is_set():
            self._thread_start_event.set()
            self._thread.start()
            logging.debug("Starting Listending to {}".format(
                str(self._consumer.topics)))         
        if wait:
            self._start_event.wait()
    
    def _stop_thread(self):
        self._stop_event.set()
        if self._thread:
            if self._thread_start_event.is_set():
                self._thread.join()
                self._thread_start_event.clear()
            self._thread = None

    def stop(self):
        self._stop_thread()
        self._consumer.stop()

    def __enter__(self):
        return self
  
    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    def configure(self, request_id = None, processor_id = None, key_property = None, keys = None):
        self._configured.clear()
        self._stop_thread()
        self._thread = threading.Thread(target=lambda :
                self._consumer.start_process(**{
                    "start_event" : self._start_event,
                    "stop_event" : self._stop_event,
                    "callback": self._process_request
                }))
        self._thread.daemon = True
        if not request_id:
            return
        self._request_id = request_id
        self._processor_id = processor_id
        self._key_property = key_property
        self._keys = keys or [self._request_id]
        self._stop_events = {}
        self._results = {}
        for key in self._keys:
            self._stop_events[key] = threading.Event()
            self._results[key] = None
        self._stop_event.clear()
        self._configured.set()
        logging.debug("Configured for Listending to {} for {}".format(
                str(self._consumer.topics), str(self._request_id))) 
        

    def get_status(self):
        if self._stop_event.is_set():
            return self._results
        try:                        
            self.start()
            self._thread.join(self._timeout)
            if self._thread.is_alive():
                self._stop_event.set()
                self._thread.join()
            return self._results
        except Exception as ex:
            logging.error("Error processing requests")    
            logging.error(ex) 
            logging.error(traceback.format_exc())         
                    

    def _process_request(self, **kwargs):
        if not self._configured.is_set():
            return
        logging.debug("Received msg: {}".format(kwargs))
        request_id = uuid.UUID(hex=kwargs['key'])
        request_id_match = request_id == self._request_id
        processor_id = kwargs['value'].get('processor_id')
        processor_id_match = not self._processor_id or self._processor_id == processor_id
        if request_id_match and processor_id_match:
            if self._key_property:
                key = uuid.UUID(hex=kwargs['value'][self._key_property])
            else:
                key = uuid.UUID(hex=kwargs['key'])
            if key in self._keys:
                logging.debug("Received status from {} : {}".format(
                    str(self._consumer.topics), str(kwargs['value'])))
                self._stop_events[key].set()
                self._results[key]=kwargs['value']
                if all(list(map(lambda e: e.is_set(), self._stop_events.values()))):
                    logging.debug("Received all status from {} for {}".format(
                        str(self._consumer.topics), str(self._keys)))
                    self._stop_event.set()
