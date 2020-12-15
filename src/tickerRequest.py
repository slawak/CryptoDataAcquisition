#!/usr/bin/python

import click
from click_mutually_exclusive_argument import MutuallyExclusiveOption
import json
import ccxt
import uuid
import logging
import threading
import traceback
import signal
import sys
import ast
import itertools
import collections

import pymongo

import simpleProducer
import simpleConsumer
from statusListener import StatusListener
import configurationService
import tickerRequestProducer

import mongoQueries

DEFAULT_CALL = "fetch_order_book"
DEFAULT_SYMBOLS = ("BTC", "ETH", "USD", "EUR")
DEFAULT_UPDATE_KEY=["lib","exchange","call","args"]
CONTROL_REQUEST_TOPIC = "ControlRequestMarketData"
STATUS_TOPIC = "StatusMarketData"
CONTROL_TIMEOUT = 60.0

DEFAULT_MONGO_CONNECTION = "mongodb://mongo:27017"
DEFAULT_MONGO_DB = "MarketData"
DEFAULT_MONGO_AUTH_MECHANISM = "SCRAM-SHA-1"      

logging.basicConfig(
                    #level=logging.DEBUG, 
                    level=logging.INFO, 
                    format='%(asctime)s - %(threadName)s -  %(name)s - %(levelname)s - %(message)s')


@click.group()
@click.option('-b', '--bootstrap_servers', envvar='BOOTSTRAP_SERVERS', help='Kafka Servers')
@click.option('-c', '--control_topic', envvar='CONTROL_TOPIC', default=CONTROL_REQUEST_TOPIC, help='Control Topic')
@click.option('-s', '--status_topic', envvar='STATUS_TOPIC', default=STATUS_TOPIC, help='Status Topic')
@click.option('-eh', '--etcd_host', envvar='ETCD_HOST', default=configurationService.DEFAULT_HOST, help='etcd host')
@click.option('-ep', '--etcd_port', envvar='ETCD_PORT', default=configurationService.DEFAULT_PORT, help='etcd port')
@click.option('-er', '--etcd_root', envvar='ETCD_ROOT', default=configurationService.DEFAULT_ETCD_ROOT, help='etcd root')
@click.option('-mc', '--mongo_connection', envvar='MONGO_CONNECTION', default=DEFAULT_MONGO_CONNECTION, help='mongo connection string')
@click.option('-mdb', '--mongo_db', envvar='MONGO_DB', default=DEFAULT_MONGO_DB, help='mongo database name')
@click.option('-ma', '--mongo_auth', envvar='MONGO_AUTH_MECHANISM', default=DEFAULT_MONGO_AUTH_MECHANISM, help='mongo database auth mechanism')
@click.option('-mu', '--mongo_user', envvar='MONGO_USER', help='mongo user name')
@click.option('-mp', '--mongo_password', envvar='MONGO_PASSWORD', help='mongo password')
@click.pass_context
def cli(ctx, bootstrap_servers, control_topic, status_topic, 
        etcd_host, etcd_port, etcd_root,
        mongo_connection, mongo_db, mongo_auth, mongo_user, mongo_password):
    ctx.obj = {**ctx.obj, **{
    "request_producer" : simpleProducer.Producer(**{
        "value.serializer" : simpleProducer.value_serializer,
        "bootstrap.servers" : bootstrap_servers,
        "send.topic" : control_topic
        }),
    "status_consumer" : simpleConsumer.Consumer(**{
        "subscribe.topics" : [status_topic],
        "value.deserializer" : simpleConsumer.value_deserializer,
        "bootstrap.servers" : bootstrap_servers,
        'group.id': uuid.uuid1(),
        'default.topic.config': {
           'auto.offset.reset': 'end'
        }
        }),
    "producer_configuration" : configurationService.EtcdConfigurationService(
            etcd_host=etcd_host, etcd_port=etcd_port,
            root=etcd_root,
            processor_type = tickerRequestProducer.PROCESSOR_TYPE,
            registration_enabled=False 
        ),
    "mongo_client" : {
                        "host" : mongo_connection,
                        "username" : mongo_user,
                        "password" : mongo_password,
                        "authSource" : mongo_db,
                        "authMechanism" : mongo_auth
    }}}

def validate_list_option(ctx, param, value):
    try:
        result = ast.literal_eval(value) if value != None else None
    except ValueError:
        result = list(value.split(','))    
    return result

@cli.command()
@click.argument('EXCHANGE', nargs=-1, type=click.STRING)
@click.option('-c','--call', type=click.STRING, help='API call')
@click.option('-l','--lib', default="ccxt", type=click.Choice(['ccxt']), help='backend library')
@click.pass_context
def checkapi(ctx, exchange, call, lib):
    '''
    Check EXCHANGE for existance of API call.
    If no call is provided just the existance of exchange is checked.
    EXCHANGE=ALL resolves to a list of all exchanges.  
    Ommiting EXCHANGE resolves to a list of all exchanges.
    EXCHANGE=ALL may be followed by exceptions, e.g. ALL EXCHANGE1 EXCHANGE2.
    '''
    exchangesList = None
    if lib == 'ccxt':
        exchangesList = ccxt.exchanges
    
    exchangeBlackList = None
    exchangeWhiteList = None
    
    if exchange and  exchange[0] == 'ALL':
        exchangeBlackList = exchange[1:]
    else:
        exchangeWhiteList = exchange
    
    if exchangeWhiteList:
        exchangesList = [ex for ex in exchangesList if ex in exchangeWhiteList]
    if exchangeBlackList:
        exchangesList = [ex for ex in exchangesList if not ex in exchangeBlackList]

    click.echo('ExchangeList is %s' % (str(exchangesList)))
    
    if not call:
        return
    
    exchanges_dict = {}
    try:    
        threads = []
        for exchange in exchangesList:
            if lib == "ccxt":         
                thread = threading.Thread(target=process_check_ccxt, 
                    kwargs={
                        "exchange": exchange,
                        "call" : call, 
                        "result_dict" : exchanges_dict
                        })
                thread.start()  
                threads.append(thread)              
    except Exception as ex:
        logging.error(ex) 
        logging.error(traceback.format_exc())         
    finally:
        for thread in threads:
            thread.join()        
    
    click.echo('Result is %s' % (str(exchanges_dict)))

def process_check_ccxt(exchange, call, result_dict):
    ex_api = getattr(ccxt, exchange)()
    if call == 'ALL':
        result_dict[exchange] = dir(ex_api)
    else:    
        result_dict[exchange] = call in dir(ex_api)

@cli.command()
@click.argument('EXCHANGE', nargs=-1, type=click.STRING)
@click.option('-c','--call', default=DEFAULT_CALL, help='API call')
@click.option('-a','--args', 
            help='Custom arguments. E.g. \'{"reload":True}\'', 
            callback=validate_list_option, cls=MutuallyExclusiveOption,  
            mutually_exclusive=["currency", "markets"])
@click.option('-m','--markets', type=click.STRING, 
            help='Markets.', 
            callback=validate_list_option, cls=MutuallyExclusiveOption,  
            mutually_exclusive=["args","currencies"])
@click.option('-s','--currencies', type=click.STRING, default=json.dumps(DEFAULT_SYMBOLS), 
            help='List of currencies.', 
            callback=validate_list_option, cls=MutuallyExclusiveOption,  
            mutually_exclusive=["args", "markets"])
@click.option('-d','--delay', type=click.FLOAT, help='Delay between requests. Defaults to exchange ratelimit.')
@click.option('-k','--key', type=click.STRING, help='Request key (defaults to LIB.EXCHANGE.CALL)')
@click.option('-l','--lib', default="ccxt", type=click.Choice(['ccxt']), help='Backend library')
@click.option('-f','--file', type=click.File('w'), help='Save resulting config to a file')
@click.option('-u','--update', default=False, is_flag=True,
            help='Update ticker list. Only start ticker wich are not yet running. Use update key to match tickers.')
@click.option('-uk','--update_key', 
            help='Key to match tickers . E.g. \'["lib","exchange","call","args"]\'', 
            default=json.dumps(DEFAULT_UPDATE_KEY),
            callback=validate_list_option)

@click.pass_context
def start(ctx, exchange, call, markets, currencies, args, delay, key, lib, file, update, update_key):
    '''
    Start sending request to EXCHANGE.
    EXCHANGE=ALL resolves to a list of all exchanges.  
    Ommiting EXCHANGE resolves to a list of all exchanges.
    EXCHANGE=ALL may be followed by exceptions, e.g. ALL EXCHANGE1 EXCHANGE2.
    '''
    exchangesList = None
    if lib == 'ccxt':
        exchangesList = ccxt.exchanges
    
    exchangeBlackList = None
    exchangeWhiteList = None
    
    if exchange and exchange[0] == 'ALL':
        exchangeBlackList = exchange[1:]
    else:
        exchangeWhiteList = exchange
    
    if exchangeWhiteList:
        exchangesList = [ex for ex in exchangesList if ex in exchangeWhiteList]
    if exchangeBlackList:
        exchangesList = [ex for ex in exchangesList if not ex in exchangeBlackList]

    click.echo('ExchangeList is %s' % (str(exchangesList)))

    status_listener = StatusListener(
        status_consumer = ctx.obj['status_consumer'],
        timeout = CONTROL_TIMEOUT)
    status_listener.start()
    
    request_id = uuid.uuid1()
    request_dict = {}
    try:    
        threads = []
        for exchange in exchangesList:
            if lib == "ccxt":        
                thread = threading.Thread(target=process_start_ccxt, 
                    kwargs={
                        "ctx" : ctx,
                        "exchange": exchange,
                        "call" : call, 
                        "markets" : markets, 
                        "currencies" : currencies, 
                        "args" : args, 
                        "delay" : delay,
                        "key" : key,
                        "request_id" : request_id,
                        "request_dict" : request_dict
                    })
                thread.start()  
                threads.append(thread)              
    except Exception as ex:
        logging.error(ex) 
        logging.error(traceback.format_exc())         
    finally:
        current_tickers = {}
        if update:
            status = getconfig_service(ctx, tickerid = None)
            if status:
                for ticker_config in status.values():
                    ticker_key = str([ticker_config[key] for key in update_key])
                    current_tickers[ticker_key] = ticker_config
            click.echo("Currently configured ticker: {}".format(str(current_tickers)))
        for thread in threads:
            thread.join()

    requests = list(itertools.chain(*request_dict.values()))

    if update:
        final_requests = []
        for request in requests:
            request_key = str([request[key] for key in update_key])
            if request_key not in current_tickers:
                final_requests.append(request)
        requests = final_requests

    status_listener.configure(
        request_id = request_id,
        key_property = 'ticker_id',
        keys = list(map(lambda r: r['ticker_id'], requests)))
    status_listener.start(wait=True)

    click.echo('Sending requests %s' % (str(requests)))
    if not requests:
        click.echo("Result {}".format(str([])))
        return        
    for request in requests:
        producer = ctx.obj['request_producer']
        producer.send(key=request['id'], value=request)
    
    status = status_listener.get_status()
    click.echo("Result {}".format(str(status)))
    if not status:
        return
    status = collections.OrderedDict((ticker, status[ticker]) for ticker in sorted(status))
    results = [result for result in status.values() if result]
    empty_results = len(status) != len(results)
    click.echo("Recieved {} results".format(len(results)))
    if empty_results:
        click.echo("Some results are empty, expected {} results. ".format(len(status)), err=True)

    if file:
        try:
            if not empty_results:
                for ticker_config in results:
                    del ticker_config['id']
                    del ticker_config['result']
                    del ticker_config['processor_id']
                json.dump(results,file, 
                    indent=4, sort_keys=True, ensure_ascii=False, 
                    default=simpleProducer.json_serial)
            else: 
                click.echo("Some results are empty. No results are saved!", err=True)
        except Exception as ex:
            logging.error(ex) 
            logging.error(traceback.format_exc())         

def process_start_ccxt(ctx, request_id, exchange, call, markets, currencies, args, delay, key, request_dict):
    lib = "ccxt"
    ex_api = getattr(ccxt, exchange)()
    if call not in dir(ex_api):
        click.echo('Exchange %s does not support %s' % (exchange, call))
        logging.debug('Exchange %s does not support %s' % (exchange, call))
        return
    try:        
        ex_api.load_markets()
        if not delay:
            delay = ex_api.rateLimit / 1000
        if not key:
            key = "{}.{}.{}".format(lib, exchange, call)
        exMarkets = ex_api.fetch_markets()
        logging.debug('Exchange %s: %s' % (exchange, str(exMarkets)))
        
        request_common = {
            "id" : request_id,
            "command" : "start",            
            "lib" : lib,
            "exchange" : exchange,
            "call" : call,
            "delay" : delay,
            "key" : key
        }

        requests = []
        if args:            
            if isinstance(args, list) and len(args) == 1:
                args = args[0]
            request = {**request_common, **{
                "ticker_id" : uuid.uuid1(), 
                "args" : args
                }}            
            requests.append(request)
        elif markets:
            for market in exMarkets:
                if (not (len(markets) == 1 and next(iter(markets)) == 'ALL') 
                    and market['symbol'] not in markets):
                    continue
                request = {**request_common, **{
                    "ticker_id" : uuid.uuid1(), 
                    "args" : {"symbol" : market['symbol']}
                    }}
                requests.append(request)
        else:
            for market in exMarkets:
                if market['base'] not in currencies or market['quote'] not in currencies:
                    continue
                request = {**request_common, **{
                    "ticker_id" : uuid.uuid1(), 
                    "args" : {"symbol" : market['symbol']}
                    }}
                requests.append(request)
        request_dict[exchange] = requests
        
    except Exception as ex:
        click.echo("Cannot send requests to exchange {}".format(exchange))    
        logging.debug(ex)
        logging.debug(traceback.format_exc())

@cli.command()
@click.argument('TICKERID', nargs=-1, type=click.STRING)
@click.pass_context
def stop(ctx, tickerid):
    '''
    Stop sending requests for TICKERID.
    Ommiting TICKERID stops ALL requests.
    '''
    try:
        status = send_command(ctx, "stop", tickerid)        
        click.echo("Result {}".format(str(status)))
        if not status:
            return
        results = [result for result in status.values() if result]
        empty_results = len(status) != len(results)
        click.echo("Recieved {} results".format(len(results)))
        if empty_results:
            click.echo("Some results are empty, expected {} results. ".format(len(status)), err=True)
    except Exception as ex:
        logging.error(ex) 
        logging.error(traceback.format_exc())         
    

def send_command(ctx, command, tickerid = None, processor_id = None):
    try:
        producer = ctx.obj['request_producer']                    
        with StatusListener(
            status_consumer = ctx.obj['status_consumer'],
            timeout = CONTROL_TIMEOUT) as status_listener:
            status_listener.start()

            if not tickerid:
                tickerid = getlist_impl(producer, status_listener, processor_id=processor_id)
                if not tickerid:
                    return

            request_common = {
                "id" : uuid.uuid1(),
                "command" : command,                        
            }

            requests = []
            for ticker_id in tickerid:
                request = {**request_common, **{
                    "ticker_id" : uuid.UUID(hex = ticker_id)
                    }}
                requests.append(request)
            
            status_listener.configure(
                request_id = request_common['id'],
                processor_id = processor_id,
                key_property = 'ticker_id',
                keys = list(map(lambda r: r['ticker_id'], requests)))
            status_listener.start(wait=True)

            click.echo('Sending requests %s' % (str(requests)))        
            for request in requests:
                producer.send(key=request['id'], value=request)
            
            status = status_listener.get_status()
            if status:
                status = collections.OrderedDict((ticker, status[ticker]) for ticker in sorted(status))
            return status
    except:
        click.echo("Cannot send requests")    
        logging.debug(traceback.format_exc())

@cli.command()
@click.option('-pid','--processor_id', type=click.STRING, help='Only return results from PROCESSOR_ID')
@click.pass_context
def getlist(ctx, processor_id):
    '''
    Retrieve a list of current TICKERIDs.    
    '''
    try:
        producer = ctx.obj['request_producer']                    
        with StatusListener(
                status_consumer = ctx.obj['status_consumer'],
                timeout = CONTROL_TIMEOUT) as status_listener:
            ticker_ids = getlist_impl(producer, status_listener, processor_id)
            click.echo('Currently running tickerids %s' % (str(ticker_ids)))        
    except Exception as ex:
        logging.error(ex) 
        logging.error(traceback.format_exc())         
        

def getlist_impl(producer, status_listener, processor_id = None):
    request_list = {
        "id" : uuid.uuid1(),
        "command" : "list",                        
    }
    status_listener.configure(request_id=request_list['id'], processor_id = processor_id)
    status_listener.start(wait=True)

    click.echo('Sending requests %s' % (str(request_list)))
    producer.send(key=request_list['id'], value=request_list)

    status = status_listener.get_status()
    click.echo("Result {}".format(str(status))) 
    
    result = status.get(request_list['id'],{})
    ticker_ids = []
    if result and "error" not in result:        
        ticker_ids = result.get('ticker_id',[])
        
    return ticker_ids

@cli.command()
@click.option('-pid','--processor_id', type=click.STRING, 
                help='Only return results from PROCESSOR_ID',
                cls=MutuallyExclusiveOption,  
                mutually_exclusive=["use_configuration_service"])
@click.option('-cs','--use_configuration_service', 
                is_flag=True, 
                default=False, 
                help='Do not sent request to producer.' + 
                'Read config from configuration service instead.',
                cls=MutuallyExclusiveOption,  
                mutually_exclusive=["processor_id"])
@click.argument('TICKERID', nargs=-1, type=click.STRING)
@click.pass_context
def getconfig(ctx, tickerid, processor_id, use_configuration_service):
    '''
    Retrieve current config for TICKERID.
    Ommiting TICKERID retrieves ALL configs.
    '''
    try:
        if use_configuration_service:
            status = getconfig_service(ctx, tickerid)
        else:
            status = send_command(ctx, "getconfig", tickerid, processor_id = processor_id)        
        click.echo("Result {}".format(str(status)))
        if not status:
            return
        results = [result for result in status.values() if result]
        empty_results = len(status) != len(results)
        click.echo("Recieved {} results".format(len(results)))
        if empty_results:
            click.echo("Some results are empty, expected {} results. ".format(len(status)), err=True)
    except Exception as ex:
        logging.error(ex) 
        logging.error(traceback.format_exc())         
    
def getconfig_service(ctx, tickerid, type="ticker"):
    configuration_service = ctx.obj['producer_configuration']
    ticker_configs, _ = configuration_service.get_config(type)
    result = {}
    for ticker in ticker_configs:
        ticker_conf = ticker_configs[ticker]
        ticker_id = ticker_conf['ticker_id']
        if not tickerid or ticker_id == tickerid:
            result[uuid.UUID(hex=ticker_id)] = ticker_conf
    if result:
        result = collections.OrderedDict((ticker, result[ticker]) for ticker in sorted(result))
    return result

@cli.command()
@click.option('-pid','--processor_id', type=click.STRING, 
                help='Only return results from PROCESSOR_ID',
                cls=MutuallyExclusiveOption,  
                mutually_exclusive=["use_configuration_service"])
@click.option('-cs','--use_configuration_service', 
                is_flag=True, 
                default=False, 
                help='Do not sent request to producer.' + 
                'Read config from configuration service instead.',
                cls=MutuallyExclusiveOption,  
                mutually_exclusive=["processor_id"])
@click.argument('FILE', type=click.File('w'), required=True)
@click.pass_context
def saveconfig(ctx, file, processor_id, use_configuration_service):
    '''
    Saves config to a FILE.
    '''
    try:
        if use_configuration_service:
            status = getconfig_service(ctx, tickerid = None)
        else:
            status = send_command(ctx, "getconfig", tickerid = None, processor_id = processor_id)        
        click.echo("Result {}".format(str(status)))
        if not status:
            return
        results = [result for result in status.values() if result]
        empty_results = len(status) != len(results)
        for ticker_config in results:
            if 'id' in ticker_config:
                del ticker_config['id']
            if 'result' in ticker_config:
                del ticker_config['result']
            del ticker_config['processor_id']
        click.echo("Recieved {} results".format(len(results)))
        if not empty_results:
            json.dump(results,file, 
                indent=4, sort_keys=True, ensure_ascii=False, 
                default=simpleProducer.json_serial)
            click.echo("Saved {} results".format(len(results)))
        else:
            click.echo(("Some results are empty, expected {} results. " + 
                        "No results are saved!").format(len(status)), err=True)
    except Exception as ex:
        logging.error(ex) 
        logging.error(traceback.format_exc())         
    

@cli.command()
@click.argument('FILE', type=click.File('r'), required=True)
@click.pass_context
def loadconfig(ctx, file):
    '''
    Load config from a FILE.
    '''
    try:
        loadconfig_from_file(ctx, file, "start")
    except Exception as ex:
        logging.error(ex) 
        logging.error(traceback.format_exc())         


def loadconfig_from_file(ctx, file, command):
    config = json.load(file)
    loadconfig_from_dict(ctx, config, command)

def loadconfig_from_dict(ctx, config, command):
    #TODO: schema validation

    if command not in [
        'start',
        'stop',
        'blacklist',
        'whitelist']:
        raise NotImplementedError("The command "  + command + " ist not implemented")

    status_listener = StatusListener(
        status_consumer = ctx.obj['status_consumer'],
        timeout = CONTROL_TIMEOUT)
    status_listener.start()
    

    request_common = {
        "id" : uuid.uuid1(),
        "command" : command
    }

    requests = []
    for ticker_config in config: 
        request = {**{
                "ticker_id" : str(uuid.uuid1())
            },
            **ticker_config, 
            **request_common
        }
        requests.append(request)
    
    status_listener.configure(
        request_id = request_common['id'],
        key_property = 'ticker_id',
        keys = list(map(lambda r: uuid.UUID(hex=r['ticker_id']), requests)))
    status_listener.start(wait=True)

    click.echo('Sending requests %s' % (str(requests)))        
    for request in requests:
        producer = ctx.obj['request_producer']
        producer.send(key=request['id'], value=request)
    
    status = status_listener.get_status()
    if status:
        status = collections.OrderedDict((ticker, status[ticker]) for ticker in sorted(status))
    click.echo("Result {}".format(str(status)))
    if status:
        results = [result for result in status.values() if result]
        empty_results = len(status) != len(results)
        click.echo("Recieved {} results".format(len(results)))
        if empty_results:
            click.echo("Some results are empty, expected {} results. ".format(len(status)), err=True)
    return status

@cli.command()
@click.argument('FILE', type=click.File('r'), required=True)
@click.pass_context
def loadblacklist(ctx, file):
    '''
    Loads blacklist config from a FILE.
    '''
    try:
        loadconfig_from_file(ctx, file, "blacklist")
    except Exception as ex:
        logging.error(ex) 
        logging.error(traceback.format_exc())         

@cli.command()
@click.argument('FILE', type=click.File('w'), required=True)
@click.pass_context
def saveblacklist(ctx, file):
    '''
    Saves blacklist config to a FILE.
    '''
    try:
        status = getconfig_service(ctx, tickerid = None, type="blacklist")
        click.echo("Result {}".format(str(status)))
        if not status:
            return
        results = [result for result in status.values() if result]
        empty_results = len(status) != len(results)
        for ticker_config in results:
            if 'id' in ticker_config:
                del ticker_config['id']
            if 'result' in ticker_config:
                del ticker_config['result']
            del ticker_config['processor_id']
        click.echo("Recieved {} results".format(len(results)))
        if not empty_results:
            json.dump(results,file, 
                indent=4, sort_keys=True, ensure_ascii=False, 
                default=simpleProducer.json_serial)
            click.echo("Saved {} results".format(len(results)))
        else:
            click.echo(("Some results are empty, expected {} results. " + 
                        "No results are saved!").format(len(status)), err=True)
    except Exception as ex:
        logging.error(ex) 
        logging.error(traceback.format_exc())         
    

@cli.command()
@click.pass_context
def getblacklist(ctx):
    '''
    Get blacklist config.
    '''
    try:
        status = getconfig_service(ctx, tickerid = None, type="blacklist")
        click.echo("Result {}".format(str(status)))
        if not status:
            return
        results = [result for result in status.values() if result]
        empty_results = len(status) != len(results)
        for ticker_config in results:
            if 'id' in ticker_config:
                del ticker_config['id']
            if 'result' in ticker_config:
                del ticker_config['result']
            del ticker_config['processor_id']
        click.echo("Recieved {} results".format(len(results)))
        if empty_results:
            click.echo("Some results are empty, expected {} results. ".format(len(status)), err=True)
    except Exception as ex:
        logging.error(ex) 
        logging.error(traceback.format_exc())         

@cli.command()
@click.option('-f','--file', type=click.File('w'), help='Save results to a file')
@click.option('-c','--command', type=click.STRING, help='Send results as a command')
@click.argument('QUERY', type=click.STRING, required=True)
@click.pass_context
def runquery(ctx, query, file, command):
    '''
    Run QUERY
    '''
    client = None
    try:
        client_data = ctx.obj['mongo_client']
        client = pymongo.MongoClient(**client_data)
        results = getattr(mongoQueries,query)(client)
        click.echo("Result {}".format(str(results)))
        if not results:
            return
        click.echo("Recieved {} results".format(len(results)))
        if file:
            json.dump(results,file, 
                indent=4, sort_keys=True, ensure_ascii=False, 
                default=simpleProducer.json_serial)
            click.echo("Saved {} results".format(len(results)))
        if command:
            loadconfig_from_dict(ctx, results, command)
    except Exception as ex:
        logging.error(ex) 
        logging.error(traceback.format_exc())
    finally:
        if client:
            client.close()        



def exit_gracefully(signum =  None, frame = None):
    for listener in StatusListener.listeners.values():
        listener.stop()
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, exit_gracefully)
    signal.signal(signal.SIGTERM, exit_gracefully)
    try:
        cli(obj={}, auto_envvar_prefix='') # pylint: disable=no-value-for-parameter, unexpected-keyword-arg
    except Exception as ex:
        logging.error(ex) 
        logging.error(traceback.format_exc())         
    finally:
        exit_gracefully()