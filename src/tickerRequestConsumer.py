#!/usr/bin/python

import threading
import time
import traceback
import confluent_kafka
import ccxt
import json
import datetime
import logging
import os
import click
import uuid
import signal
import queue
import collections
import etcd3

import simpleProducer
import simpleConsumer
import heartbeatProducer
import configurationService

from ccxtRequestProcessor import CcxtRequestProcessor

logging.basicConfig(
                    #level=logging.DEBUG, 
                    level=logging.INFO, 
                    format='%(asctime)s - %(threadName)s -  %(name)s - %(levelname)s - %(message)s')

REQUEST_MARKET_DATA_TOPIC = "RequestMarketData"
RESULT_MARKET_DATA_TOPIC = "ResultMarketData"
STATUS_TOPIC = "StatusMarketData"

PROCESSOR_TYPE = "TickerRequestConsumer"

STOP_THREADS = threading.Event()

class RequestListener(object):
    def __init__(self, consumer, result_producer, status_producer, id, stop_event,
            etcd_host, etcd_port, etcd_root):
        self.id = id
        self._consumer = consumer   
        self._result_producer = result_producer  
        self._status_producer = status_producer      
        self._stop_event = stop_event
        self._thread = threading.Thread(target=self.run)                
        self._heartbeat = heartbeatProducer.HeatbeatProducer(
            status_producer = self._status_producer,
            delay = 1, id = self.id, 
            stop_event = self._stop_event,
            processor_type = PROCESSOR_TYPE
        )
        self._configuration_service = configurationService.EtcdConfigurationService(
            etcd_host=etcd_host, etcd_port=etcd_port,
            root=etcd_root,
            id = self.id, 
            stop_event = STOP_THREADS,
            processor_type = PROCESSOR_TYPE,
            leader_election_enabled = False 
        )
        self.processors = {}

    def start(self):
        logging.info("Start recieving msg from {}".format(
            self._consumer.topics))        
        self._heartbeat.start()
        self._configuration_service.start()
        self._thread.start()     

    def run(self):
        try:
            self._consumer.consume(**{
                "stop_event" : self._stop_event,
                "callback": self.process_request
            })
        except Exception as ex:   
            logging.error("Error processing requests")               
            logging.error(ex)             
            logging.debug(traceback.format_exc())
        finally:
            for processor in self.processors.values():
                processor.stop()
            for processor in self.processors.values():
                processor._thread.join()

    def process_request(self, **kwargs):
        try:            
            key = kwargs['key']
            request = kwargs['value']
            lib = request['lib']        
            exchange = request['exchange']
            processor_key = "{}.{}".format(lib, exchange)

            logging.debug("Received msg: {}".format(kwargs))
            logging.info("Received msg: {}".format({k:kwargs[k] for k in kwargs if k not in set(['value'])}))
                        
            if processor_key in self.processors:
                processor = self.processors[processor_key]
            else:
                if lib == "ccxt":
                    processor = CcxtRequestProcessor(
                        producer = self._result_producer,
                        status_producer = self._status_producer,
                        configuration_service = self._configuration_service,
                        listener_id = self.id,
                        exchange = exchange,
                        initial_key = key,
                        initial_request = request
                    )
                    self.processors[processor_key] = processor
                    processor.start()
                else:
                    raise NotImplementedError("Library {} is not supported".format(lib))

            processor.put(kwargs)
        except Exception as ex:   
            msg = "Error processing request" 
            logging.error(msg)            
            logging.debug(ex) 
            trace = traceback.format_exc() 
            logging.debug(trace)
            self._send_status_error(msg, self.id, request, ex, trace)   


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
                    "processor_id" : self.id
                }
            self._status_producer.send(key=key, value=status)
        except Exception as ex:
            logging.error("Error sending status")    
            logging.debug(ex) 
            logging.debug(traceback.format_exc())
    

@click.command()
@click.option('-b', '--bootstrap_servers', envvar='BOOTSTRAP_SERVERS', help='Kafka Servers')
@click.option('-o', '--result_topic', envvar='RESULT_TOPIC', default=RESULT_MARKET_DATA_TOPIC, help='Result Topic')
@click.option('-rid', '--request_id', envvar='REQUEST_ID', default=str(uuid.uuid1()), help='Control Id')
@click.option('-s', '--status_topic', envvar='STATUS_TOPIC', default=STATUS_TOPIC, help='Status Topic')
@click.option('-r', '--request_topic', envvar='REQUEST_TOPIC', default=REQUEST_MARKET_DATA_TOPIC, help='Request Topic')
@click.option('-eh', '--etcd_host', envvar='ETCD_HOST', default=configurationService.DEFAULT_HOST, help='etcd host')
@click.option('-ep', '--etcd_port', envvar='ETCD_PORT', default=configurationService.DEFAULT_PORT, help='etcd port')
@click.option('-er', '--etcd_root', envvar='ETCD_ROOT', default=configurationService.DEFAULT_ETCD_ROOT, help='etcd root')
def start_contoller(bootstrap_servers, result_topic, request_id, status_topic, request_topic,
                    etcd_host, etcd_port, etcd_root):
    '''
    Consumer for periodic requests.
    Listenes to REQUEST_TOPIC for requests on starting and controlling producers.
    Producers are sending periodic requests on RESULT_TOPIC topic
    '''
    REQUEST_MARKET_DATA_CONSUMER = simpleConsumer.Consumer(**{
        "subscribe.topics" : [request_topic],
        "value.deserializer" : simpleConsumer.value_deserializer,
        "bootstrap.servers" : bootstrap_servers,
        'group.id': request_id
        })
    RESULT_MARKET_DATA_PRODUCER = simpleProducer.Producer(**{
        "value.serializer" : simpleProducer.value_serializer,
        "bootstrap.servers" : bootstrap_servers,
        "send.topic" : result_topic
        })
    STATUS_PRODUCER = simpleProducer.Producer(**{
        "value.serializer" : simpleProducer.value_serializer,
        "bootstrap.servers" : bootstrap_servers,
        "send.topic" : status_topic
        })

    try:
        processor = RequestListener(
            consumer=REQUEST_MARKET_DATA_CONSUMER, 
            result_producer=RESULT_MARKET_DATA_PRODUCER,
            status_producer=STATUS_PRODUCER,
            id = uuid.uuid1(),
            stop_event = STOP_THREADS,
            etcd_host=etcd_host,
            etcd_port=etcd_port,
            etcd_root=etcd_root)
        processor.start()
    except: 
        STOP_THREADS.set()        
        logging.error(traceback.format_exc())    
    finally:
        processor._thread.join()

def exit_gracefully(signum =  None, frame = None):
    STOP_THREADS.set()

if __name__ == '__main__':
    signal.signal(signal.SIGINT, exit_gracefully)
    signal.signal(signal.SIGTERM, exit_gracefully)

    start_contoller() # pylint: disable=no-value-for-parameter