import threading
import time
import traceback
import ccxt
import json
import datetime
import dateutil.parser
import logging
import os
import uuid
import etcd3

import simpleProducer
import configurationService


class TickerProducer(object):
    def __init__(self, request_producer,
            status_producer, 
            configuration_service,
            processor_id, ticker_id, 
            exchange, call, args, delay, key, lib, 
            sequence_nr = 0, last_ticker = None):
        self.processor_id = processor_id
        self._request_producer = request_producer
        self._status_producer = status_producer
        self._configuration_service = configuration_service
        self.ticker_id = ticker_id
        self.exchange = exchange
        self.call = call
        self.args = args
        self.delay = delay
        self.key = key
        self.sequence_nr = sequence_nr
        self.lib = lib
        if isinstance(last_ticker, datetime.datetime):
            self.last_ticker = last_ticker
        elif isinstance(last_ticker,str):
            self.last_ticker = dateutil.parser.parse(last_ticker)
        else:
            self.last_ticker = None
        
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self.request_ticker_data, daemon=True)

    def get_config(self):
        return dict([(k,v) for k,v in self.__dict__.items() if not k.startswith('_')])

    def start(self):
        self._thread.start()        

    def stop(self, deregister=False):
        self._stop.set()
        if deregister:
            self.deregister()

    def register(self):
        logging.info("Register ticker config {}".format(self.ticker_id))
        self._configuration_service.put_status(
            "ticker",
            str(self.ticker_id), 
            {
                "id" : self.ticker_id,
                "start_time" : datetime.datetime.now()
            })
        self.put_config()

    def put_config(self):
        config = self.get_config()
        if self._configuration_service.leader_event.is_set():
            self._configuration_service.put_config(
                configurationService.combine_path([
                    "ticker",self.exchange,self.call,str(self.args).replace('/','_')
                ]),
                str(self.ticker_id), 
                config)
        return config

    def deregister(self):
        logging.info("Deregister ticker config {}".format(self.ticker_id))
        self._configuration_service.del_status(
            "ticker",
            str(self.ticker_id))
        if self._configuration_service.leader_event.is_set():
            self._configuration_service.del_config(
                configurationService.combine_path([
                    "ticker",self.exchange,self.call,str(self.args).replace('/','_')
                ]),
                str(self.ticker_id))

    def request_ticker_data(self):
        try: 
            logging.info("Start sending {} requests to {} for {}".format(
                self.call, self.exchange, self.args))
            stop_condition = self._stop.is_set()
            self.register()
            if self.last_ticker:
                next_ticker = self.last_ticker + datetime.timedelta(0,self.delay)
                time_to_next = (next_ticker - datetime.datetime.now()).total_seconds()
                if time_to_next > 0:
                    logging.info("Delaying start sending {} requests to {} for {} by {} seconds".format(
                        self.call, self.exchange, self.args, time_to_next))
                    stop_condition = self._stop.wait(time_to_next)
            while not stop_condition:
                self.last_ticker = datetime.datetime.now()
                request={
                    "ticker_id" : self.ticker_id,
                    "request_id" : uuid.uuid1(),
                    "sequence_nr" : self.sequence_nr,
                    "processor_id" : self.processor_id,
                    "key" : self.key,
                    "exchange": self.exchange, 
                    "call" : self.call, 
                    "args" : self.args, 
                    "lib" : self.lib,
                    "request_timestamp" : self.last_ticker
                }
                logging.debug("Sending request {}".format(request))
                try:
                    if self._configuration_service.leader_event.is_set():
                        self._request_producer.send( 
                            key=request['request_id'], 
                            value=request)
                    self.sequence_nr += 1                  
                except Exception as ex:
                    logging.error("Error sending requests to exchange {}".format(self.exchange))    
                    logging.debug(ex) 
                    logging.debug(traceback.format_exc())
                stop_condition = self._stop.wait(self.delay)
                            
            logging.info("Stop sending {} requests to {} for {}".format(
                self.call, self.exchange, self.args))
        except Exception as ex:
            msg = "Error sending requests to exchange {}".format(self.exchange)
            logging.error(msg)    
            logging.debug(ex)
            trace = traceback.format_exc() 
            logging.debug(trace)
            self._send_status_error(msg, self.key, ex, trace) 
    
    def _send_status_error(self, msg, key, exception, trace):
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
                        "config" : str(self.get_config()),
                        "message" : msg
                    },
                    "error" : True,
                    "ticker_id" : self.ticker_id,
                    "processor_id" : self.processor_id
                }
            self._status_producer.send(key=key, value=status)
        except Exception as ex:
            logging.error("Error sending status")    
            logging.debug(ex) 
            logging.debug(traceback.format_exc()) 
