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
import etcd3
import concurrent.futures
import os
import collections

import simpleProducer
import simpleConsumer
import heartbeatProducer
import configurationService

from tickerProducer import TickerProducer

CONTROL_REQUEST_TOPIC = "ControlRequestMarketData"
STATUS_TOPIC = "StatusMarketData"
REQUEST_MARKET_DATA_TOPIC = "RequestMarketData"
PROCESSOR_TYPE = "TickerRequestProducer"

REFRESH_CONFIG_DELAY = 600

TICKER_KEY=["lib","exchange","call","args"]

logging.basicConfig(
                    #level=logging.DEBUG, 
                    level=logging.INFO, 
                    format='%(asctime)s - %(threadName)s -  %(name)s - %(levelname)s - %(message)s')


REQUEST_MARKET_DATA_PRODUCER = None
STATUS_PRODUCER = None

STOP_THREADS = threading.Event()

def get_ticker_key(ticker):
    return str([ticker[key] for key in TICKER_KEY])
        
class RequestProcessor(object):
    def __init__(self, control_consumer, request_producer, status_producer, 
                etcd_host, etcd_port, etcd_root, processor_id = None):
        self._control_consumer = control_consumer   
        self._request_producer = request_producer   
        self._status_producer = status_producer
        self._processor_id = processor_id or uuid.uuid1()
        self._thread = threading.Thread(target=self._run)
        self._refresh_config_thread = threading.Thread(target=self._run_refresh_config, daemon = True)
        self._ticker_by_id = {}
        self._ticker_by_key = collections.defaultdict(dict)
        self._heartbeat = heartbeatProducer.HeatbeatProducer(
            status_producer = self._status_producer,
            delay = 1, 
            id = self._processor_id, 
            stop_event = STOP_THREADS,
            processor_type = PROCESSOR_TYPE
        )
        self._configuration_service = configurationService.EtcdConfigurationService(
            etcd_host=etcd_host, etcd_port=etcd_port,
            root=etcd_root,
            id = self._processor_id, 
            stop_event = STOP_THREADS,
            processor_type = PROCESSOR_TYPE 
        )
        self._configuration_service.register_callback = lambda : self._async_process_request(self._get_config)
        workers = os.cpu_count()
        if workers:
            workers = workers * 20
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)

    def _upsert_ticker(self, id, ticker):
        key = get_ticker_key(ticker.get_config())
        self._ticker_by_id[id] = ticker
        self._ticker_by_key[key][id] = ticker

    def _remove_ticker_by_id(self, id):
        ticker = self._ticker_by_id[id]
        key = get_ticker_key(ticker.get_config())
        del self._ticker_by_id[id]
        del self._ticker_by_key[key][id]

    def _list_ticker(self, key = None):
        if key == None:
            return self._ticker_by_id.values()
        else:
            return self._ticker_by_key[key].values()

    def _list_ticker_ids(self, key = None):
        if key == None:
            return self._ticker_by_id.keys()
        else:
            return self._ticker_by_key[key].keys() 

    def _get_ticker(self, id):
        return self._ticker_by_id[id]

    def _refresh_config(self):
        try:
            for ticker in list(self._list_ticker()):
                ticker.put_config()
        except Exception as ex:            
            logging.error(ex) 
            logging.debug(traceback.format_exc())

    def _run_refresh_config(self):
        while not STOP_THREADS.wait(REFRESH_CONFIG_DELAY):
            self._refresh_config()
    
    def _run(self):
        try:
            self._control_consumer.consume(**{
                "stop_event" : STOP_THREADS,
                "callback": self._process_request
            })
        except Exception as ex:            
            logging.error(ex) 
            logging.debug(traceback.format_exc())
        finally:
            for ticker in self._list_ticker():
                ticker.stop()               

    def _async_process_request(self, call, **kwargs):
        self._executor.submit(self._async_process_request_impl, call, **kwargs)

    def _async_process_request_impl(self, call, **kwargs):
        kwargs = {**{
            'request' : None,
            'key' : uuid.uuid1()
        },**kwargs}
        try:
            request = kwargs['request']
            key = kwargs['key']
            call(**kwargs)
        except Exception as ex:
            msg = "Error processing request" 
            logging.error(msg)            
            logging.debug(ex) 
            trace = traceback.format_exc() 
            logging.debug(trace)
            self._send_status_error(msg, key, request, ex, trace)   
    
    def _process_request(self, **kwargs):
        logging.info("Received msg: {}".format(kwargs))
        request = kwargs['value']
        key = kwargs['key']
        try:
            command = request['command']
            del request['command']
            if not command.startswith('_'):
                del request['id']
                self._async_process_request(
                    call = getattr(self, command),
                    **{
                        'key' : uuid.UUID(hex=key), 
                        'request' : request
                    })
        except Exception as ex:
            msg = "Error processing request" 
            logging.error(msg)            
            logging.debug(ex) 
            trace = traceback.format_exc() 
            logging.debug(trace)
            self._send_status_error(msg, key, request, ex, trace)

    def _start(self):
        logging.info("Start recieving msg from {}".format(
            self._control_consumer.topics))        
        self._heartbeat.start()
        self._configuration_service.start()
        self._thread.start()
        self._refresh_config_thread.start()

    def _get_config(self, **kwargs):
        logging.info("Retrieving stored ticker configuration")
        try:
            ticker_configs, _ = self._configuration_service.get_config("ticker")
        except Exception as ex:
                msg = "Error retrieving stored ticker data" 
                logging.error(msg)            
                logging.debug(ex) 
                trace = traceback.format_exc() 
                logging.debug(trace)
                self._send_status_error(msg, self._processor_id, None, ex, trace)
                return
        for ticker in ticker_configs:
            if STOP_THREADS.is_set():
                return
            try:
                self.start(self._processor_id, ticker_configs[ticker])
            except Exception as ex:
                msg = "Error configuring stored ticker" 
                logging.error(msg)            
                logging.debug(ex) 
                trace = traceback.format_exc() 
                logging.debug(trace)
                self._send_status_error(msg, self._processor_id, ticker_configs[ticker], ex, trace)   

    def blacklist(self, key, request):
        exchange = request['exchange']
        call = request['call']
        args = request['args']
        ticker_id = request['ticker_id']
        request["processor_id"] = self._processor_id
        for ticker in list(self._list_ticker(get_ticker_key(request))):
            self.stop(key, ticker.get_config())
        if self._configuration_service.leader_event.is_set():
            current, _ = self._configuration_service.get_config(
                configurationService.combine_path([
                    "blacklist",exchange,call,str(args).replace('/','_')
                ]))
            for config in current.values():
                old_ticker_id = config['ticker_id']
                self._configuration_service.del_config(
                    configurationService.combine_path([
                        "blacklist",exchange,call,str(args).replace('/','_')
                    ]),
                    old_ticker_id)
            self._configuration_service.put_config(
                configurationService.combine_path([
                    "blacklist",exchange,call,str(args).replace('/','_')
                ]),
                ticker_id, 
                request)
            status = {**request, **{
                "id" : key,
                "result": "blacklist"
            }}
            self._status_producer.send(key=key, value=status) 

    def whitelist(self, key, request):
        exchange = request['exchange']
        call = request['call']
        args = request['args']
        request["processor_id"] = self._processor_id
        if self._configuration_service.leader_event.is_set():
            current, _ = self._configuration_service.get_config(
                configurationService.combine_path([
                    "blacklist",exchange,call,str(args).replace('/','_')
                ]))
            for config in current.values():
                old_ticker_id = config['ticker_id']
                self._configuration_service.del_config(
                    configurationService.combine_path([
                        "blacklist",exchange,call,str(args).replace('/','_')
                    ]),
                    old_ticker_id)
            status = {**request, **{
                "id" : key,
                "result": "whitelist"
            }}
            self._status_producer.send(key=key, value=status)

    def _check_blacklisted(self, request):
        exchange = request['exchange']
        call = request['call']
        args = request['args']
        request_key = get_ticker_key(request)
        current, _ = self._configuration_service.get_config(
            configurationService.combine_path([
                "blacklist",exchange,call,str(args).replace('/','_')
            ]))
        blacklisted = False
        for config in current.values():
            blacklist_key = get_ticker_key(config)
            if request_key == blacklist_key:
                blacklisted = True
                break
        return blacklisted

    def start(self, key, request):
        ticker_id =  request['ticker_id']
        if self._check_blacklisted(request):
            status = {**request, **{
                "id" : key,
                "processor_id" : self._processor_id,
                "result": "blacklisted"
            }}
        else:
            if ticker_id in self._list_ticker_ids():
                self._get_ticker(ticker_id).stop(deregister=True)
            self._upsert_ticker(ticker_id, TickerProducer(
                self._request_producer,
                self._status_producer, 
                self._configuration_service,
                **{**request, **{
                    "processor_id" : self._processor_id
                }}))
            self._get_ticker(ticker_id).start()
            status = self._get_ticker(ticker_id).get_config()
            status = {**status, **{
                "id" : key,
                "result": "start"
            }}
        self._status_producer.send(key=key, value=status)

    def stop(self, key, request):
        ticker_id =  request['ticker_id']
        if ticker_id in self._list_ticker_ids():
            self._get_ticker(ticker_id).stop(deregister=True)
            status = {
                "id" : key,
                "result": "stop",
                "ticker_id" : ticker_id,
                "processor_id" : self._processor_id
            }
            self._remove_ticker_by_id(ticker_id)
        else:            
            status = {
                "id" : key,
                "result" : "ticker_id_not_found",
                "error" : True,
                "ticker_id" : ticker_id,
                "processor_id" : self._processor_id
            }
        self._status_producer.send(key=key, value=status)

    def list(self, key, request):
        status = {
            "id" : key,
            "processor_id" : self._processor_id,
            "result" : "list",            
            "ticker_id" : list(self._list_ticker_ids())
        }
        self._status_producer.send(key=key, value=status)

    def getconfig(self, key, request):
        ticker_id =  request['ticker_id']
        if ticker_id in self._list_ticker_ids():
            status = self._get_ticker(ticker_id).put_config()
            status = {**status, **{
                "id" : key,
                "result": "config"
            }}
        else:
            status = {
                "id" : key,
                "result": "ticker_id_not_found",
                "error" : True,
                "ticker_id" : ticker_id,
                "processor_id" : self._processor_id
            }
        self._status_producer.send(key=key, value=status)

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
                    "processor_id" : self._processor_id
                }
            self._status_producer.send(key=key, value=status)
        except Exception as ex:
            logging.error("Error sending status")    
            logging.debug(ex) 
            logging.debug(traceback.format_exc()) 
    



@click.command()
@click.option('-b', '--bootstrap_servers', envvar='BOOTSTRAP_SERVERS', help='Kafka Servers')
@click.option('-c', '--control_topic', envvar='CONTROL_TOPIC', default=CONTROL_REQUEST_TOPIC, help='Control Topic')
@click.option('-cid', '--control_id', envvar='CONTROL_ID', default=str(uuid.uuid1()), help='Control Id')
@click.option('-s', '--status_topic', envvar='STATUS_TOPIC', default=STATUS_TOPIC, help='Status Topic')
@click.option('-r', '--request_topic', envvar='REQUEST_TOPIC', default=REQUEST_MARKET_DATA_TOPIC, help='Request Data Topic')
@click.option('-eh', '--etcd_host', envvar='ETCD_HOST', default=configurationService.DEFAULT_HOST, help='etcd host')
@click.option('-ep', '--etcd_port', envvar='ETCD_PORT', default=configurationService.DEFAULT_PORT, help='etcd port')
@click.option('-er', '--etcd_root', envvar='ETCD_ROOT', default=configurationService.DEFAULT_ETCD_ROOT, help='etcd root')
def start_contoller(bootstrap_servers, control_topic, control_id, status_topic, request_topic,
                    etcd_host, etcd_port, etcd_root):
    '''
    Producer for periodic requests.
    Listenes to CONTROL_TOPIC for requests on starting and controlling producers.
    Producers are sending periodic requests on REQUEST_TOPIC topic
    '''
    CONTROL_REQUEST_CONSUMER = simpleConsumer.Consumer(**{
        "subscribe.topics" : [control_topic],
        "value.deserializer" : simpleConsumer.value_deserializer,
        "bootstrap.servers" : bootstrap_servers,
        'group.id': control_id
        })
    REQUEST_MARKET_DATA_PRODUCER = simpleProducer.Producer(**{
        "value.serializer" : simpleProducer.value_serializer,
        "bootstrap.servers" : bootstrap_servers,
        "send.topic" : request_topic
        })
    STATUS_PRODUCER = simpleProducer.Producer(**{
        "value.serializer" : simpleProducer.value_serializer,
        "bootstrap.servers" : bootstrap_servers,
        "send.topic" : status_topic
        })

    try:
        processor = RequestProcessor(
            control_consumer=CONTROL_REQUEST_CONSUMER, 
            request_producer=REQUEST_MARKET_DATA_PRODUCER,
            status_producer=STATUS_PRODUCER,
            etcd_host=etcd_host,
            etcd_port=etcd_port,
            etcd_root=etcd_root)        
        processor._start()
        processor._thread.join()
    except Exception as ex:            
        logging.error(ex) 
        logging.debug(traceback.format_exc()) 
    finally:
        STOP_THREADS.set()
        for ticker in processor._list_ticker():
            ticker._thread.join()
        processor._thread.join()
        processor._executor.shutdown()

def exit_gracefully(signum =  None, frame = None):
    STOP_THREADS.set()

if __name__ == '__main__':
    signal.signal(signal.SIGINT, exit_gracefully)
    signal.signal(signal.SIGTERM, exit_gracefully)
    
    start_contoller() # pylint: disable=no-value-for-parameter
