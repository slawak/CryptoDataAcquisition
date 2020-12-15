import threading
import time
import traceback
import ccxt
import json
import datetime
import logging
import os
import click
import uuid
import queue
import collections
import etcd3

import simpleProducer
import configurationService

STOP_REQUEST = "StopRequest"
MAX_REQUEST_LAG = 100

class CcxtRequestProcessor(object):
    def __init__(self, producer, status_producer, configuration_service,
            listener_id, exchange, initial_key, initial_request):
        self.exchange = exchange
        self.queue = queue.Queue()         
        self.key_counter = collections.Counter()
        self._listener_id = listener_id
        self._initial_key = initial_key,
        self._initial_request = initial_request,
        self._producer = producer
        self._status_producer = status_producer
        self._configuration_service = configuration_service
        self._exchange_api = None
        self._thread = threading.Thread(target=self.run, daemon = True)    

    def start(self):
        self._thread.start()

    def stop(self):
        self.queue.put(STOP_REQUEST)

    def put(self, request):
        lib = request['value']['lib']
        exchange = request['value']['exchange']                
        call = request['value']['call']
        args = request['value']['args']
        processor_key = "{}.{}.{}.({})".format(lib, exchange, call, str(args))
        self.key_counter[processor_key] += 1
        request['processor_key'] = processor_key
        request['request_sequence_nr'] = self.key_counter[processor_key]
        self.queue.put(request)
    
    def run(self):
        try:
            self._exchange_api = getattr(ccxt, self.exchange)()
            self._configuration_service.put_status(
                "exchange",
                "{}.{}".format("ccxt", self.exchange), 
                {
                    "lib" : "ccxt",
                    "exchange" : self.exchange,
                    "start_time" : datetime.datetime.now()
                })
            
            while True:
                request = None
                try:
                    request = self.queue.get(block = True)
                    request_value = request['value']
                    if request == STOP_REQUEST:
                        break
                    self.process_request(**request)
                    self.queue.task_done()
                except Exception as ex:   
                    msg = "Error processing requests to exchange {}".format(self.exchange) 
                    logging.error(msg)            
                    logging.debug(ex) 
                    trace = traceback.format_exc() 
                    logging.debug(trace)
                    self._send_status_error(msg, self._listener_id, request_value, ex, trace)        
        except Exception as ex:            
            msg = "Error processing requests to exchange {}".format(self.exchange) 
            logging.error(msg)            
            logging.debug(ex) 
            trace = traceback.format_exc() 
            logging.debug(trace)
            self._send_status_error(msg, self._initial_key, self._initial_request, ex, trace)
            

    def process_request(self, **kwargs):
        request = kwargs['value']
        lib = kwargs['value']['lib']        
        exchange = kwargs['value']['exchange']                
        call = kwargs['value']['call']
        args = kwargs['value']['args']
        key = kwargs['value']['key']

        assert lib == "ccxt"
        assert exchange == self.exchange      

        processor_key = kwargs['processor_key']
        request_sequence_nr = kwargs['request_sequence_nr']
        current_sequence_nr = self.key_counter[processor_key]

        # skip requests if there are more requests with same key in queue
        # allow some lag to ensure at least some requests are always processed
        warning = None
        skip = False
        if request_sequence_nr < current_sequence_nr - MAX_REQUEST_LAG:
            skip = True
            warning_dict = {
                'processor_key' : processor_key, 
                'request_sequence_nr' :request_sequence_nr, 
                'current_sequence_nr' : current_sequence_nr
            }
            msg = "Skipping request with processor_key={processor_key}, " \
                  "request_sequence_nr={request_sequence_nr}, " \
                  "current_sequence_nr={current_sequence_nr}".format(**warning_dict)
            logging.warn(msg) 
            warning = self._send_status_warn(msg, self._listener_id, request, warning_dict)

        if 'request_timestamp' in kwargs['value']:
            request_timestamp = kwargs['value']['request_timestamp']
        else:
            request_timestamp = kwargs['timestamp']
        request_result = None
        error = None
        if not skip:
            try:            
                request_result = getattr(self._exchange_api,call)(**args)
                self.fix_keys(request_result)
            except Exception as ex:                        
                msg = "Error processing requests to exchange {}".format(self.exchange) 
                logging.error(msg)            
                logging.debug(ex) 
                trace = traceback.format_exc() 
                logging.debug(trace)
                error = self._send_status_error(msg, self._listener_id, request, ex, trace)        
        result={
            "exchange": exchange, 
            "call": call, 
            "args": args,
            "request_timestamp" : request_timestamp,
            "call_timestamp" : kwargs['rec_timestamp'],
            "result_timestamp" : datetime.datetime.now(),
            "result" : request_result,
            "ticker_id" : kwargs['value']['ticker_id'],
            "key" : key,
            "request_id" : kwargs['value']['request_id'],
            "sequence_nr" : kwargs['value']['sequence_nr'],
            "request_processor_id" : kwargs['value']['processor_id'],
            "result_processor_id" : self._listener_id,
            "lib" : lib
        }
        if warning:
            del warning['details']['request']
            result = {**result, **{
                "warning" : warning['details'],
                "status" : "warning"
            }}         
        if error:
            del error['details']['request']
            result = {**result, **{
                "error" : error['details'],
                "status" : "error"
            }}
        
        logging.debug("Sending result {}".format(result))
        logging.info("Sending result {}".format({k:result[k] for k in result if k not in set([
            'result','call','args','lib'])}))

        try:
            self._producer.send(
                key=key,                
                value=result)
        except Exception as ex:            
            msg = "Error processing requests to exchange {}".format(self.exchange) 
            logging.error(msg)            
            logging.debug(ex) 
            trace = traceback.format_exc() 
            logging.debug(trace)
            self._send_status_error(msg, self._listener_id, request, ex, trace)

    def fix_keys(self, dictionary, match='.', replace_by='&#46;'):
        if isinstance(dictionary, str):
            return
        if isinstance(dictionary, collections.abc.Mapping):
            for k in list(dictionary.keys()):
                if isinstance(dictionary[k], collections.abc.Mapping):
                    self.fix_keys(dictionary[k], match, replace_by)
                elif isinstance(dictionary[k], collections.abc.Sequence):
                    self.fix_keys(dictionary[k], match, replace_by)
                if isinstance(k, str) and k.find(match) > -1:
                    logging.debug("Fixing key {}".format(k))
                    value = dictionary[k]
                    new_key = k.replace(match, replace_by)
                    del dictionary[k] 
                    dictionary[new_key] = value
                    logging.debug("Fixed key {}".format(new_key))
        elif isinstance(dictionary, collections.abc.Sequence):        
            for item in dictionary:
                self.fix_keys(item, match, replace_by)
        
    def _send_status_error(self, msg, key, request, exception, trace):
        try:
            if isinstance(key, bytes):
                try:
                    key = uuid.UUID(bytes=key)
                except:
                    key = str(key)
            status = {
                    "id" : key,
                    "result" : "exception",
                    "details" : {
                        "exception" : str(exception),
                        "type" : str(type(exception)),
                        "trace" : str(trace),
                        "request" : request,
                        "message" : msg
                    },
                    "error" : True,
                    "processor_id" : self._listener_id
                }
            self._status_producer.send(key=key, value=status)
            return status
        except Exception as ex:
            logging.error("Error sending status")    
            logging.debug(ex) 
            logging.debug(traceback.format_exc())  

    def _send_status_warn(self, msg, key, request, warning_dict):
        try:
            if isinstance(key, bytes):
                try:
                    key = uuid.UUID(bytes=key)
                except:
                    key = str(key)
            status = {
                    "id" : key,
                    "result" : "warning",
                    "details" : {**{
                        "request" : request,
                        "message" : msg
                    }, **warning_dict},
                    "warning" : True,
                    "processor_id" : self._listener_id
                }
            self._status_producer.send(key=key, value=status)
            return status
        except Exception as ex:
            logging.error("Error sending status")    
            logging.debug(ex) 
            logging.debug(traceback.format_exc())    

